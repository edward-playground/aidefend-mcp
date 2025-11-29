
from fastembed import TextEmbedding

print("Supported models:")
for model in TextEmbedding.list_supported_models():
    print(f"- {model['model']}")
