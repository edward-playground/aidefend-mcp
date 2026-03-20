# Advanced Configuration Guide

This guide covers advanced customization topics for AIDEFEND MCP, including how to switch embedding models and register custom models.

## Changing Embedding Models

AIDEFEND uses [FastEmbed](https://github.com/qdrant/fastembed) for local embedding generation. You can switch models to support different languages, performance profiles, or dimensions.

### Scenario A: Using a Natively Supported Model

FastEmbed supports many popular models out-of-the-box (e.g., `BAAI/bge-small-en-v1.5`, `intfloat/multilingual-e5-large`).

1.  **Check Supported Models**:
    Run this Python snippet to see available models:
    ```python
    from fastembed import TextEmbedding
    for model in TextEmbedding.list_supported_models():
        print(model['model'])
    ```

2.  **Update Configuration**:
    Edit your `.env` file:
    ```bash
    # Example: Switching to a larger multilingual model
    EMBEDDING_MODEL=intfloat/multilingual-e5-large
    EMBEDDING_DIMENSION=1024  # Must match the new model's dimension
    ```

3.  **Rebuild Database**:
    Since vector dimensions must match, you must rebuild the database when changing models:
    ```bash
    # Windows
    Remove-Item -Recurse -Force data/aidefend_kb.lancedb
    Remove-Item -Force data/local_version.json
    
    # Restart service to trigger re-sync
    python -m app.main
    ```

---

### Scenario B: Using a Custom or Unsupported Model

If you want to use a model that isn't in the default FastEmbed list, you need to **register** it in the code.

**Note**: `Xenova/multilingual-e5-base` is the **default** model and is already registered - no custom configuration needed.

**Example**: Using a different ONNX model like `intfloat/multilingual-e5-small` or another custom model.

#### Step 1: Update Configuration
Edit `.env`:
```bash
EMBEDDING_MODEL=my-custom/model-name
EMBEDDING_DIMENSION=768
```

#### Step 2: Register Model in Code
You need to modify **two files** to register the custom model before it's used.

**File 1: `app/core.py`**
Locate `_register_custom_embedding_models()` and add your model:

```python
# app/core.py

def _register_custom_embedding_models():
    # ... existing code ...
    
    # Add your custom model
    TextEmbedding.add_custom_model(
        model="my-custom/model-name",
        pooling=PoolingType.MEAN,  # or CLS, depending on model
        normalization=True,
        sources=ModelSource(hf="my-custom/model-name"), # HuggingFace ID
        dim=768,
        model_file="onnx/model.onnx", # Path within the HF repo
        description="My Custom Model",
        license="MIT"
    )
```

**File 2: `app/sync.py`**
Locate `_register_custom_embedding_models_for_sync()` and add the **exact same code** as above.
*(Note: This duplication exists to prevent circular import issues during the sync process.)*

#### Step 3: Update Known Models (Optional but Recommended)
In `app/core.py`, update the `KNOWN_EMBEDDING_MODELS` dictionary. This helps the system detect model mismatches.

```python
# app/core.py

KNOWN_EMBEDDING_MODELS: Dict[str, int] = {
    "Xenova/multilingual-e5-base": 768,
    "my-custom/model-name": 768,  # Add your model here
    # ...
}
```

#### Step 4: Rebuild Database
Follow the same rebuild steps as Scenario A.

## Troubleshooting

- **Dimension Mismatch**: If you see errors about vector dimension mismatch, ensure `EMBEDDING_DIMENSION` in `.env` matches your model's output size.
- **Model Not Found**: If FastEmbed can't find your model, ensure you've registered it in **both** `app/core.py` and `app/sync.py`.
