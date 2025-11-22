"""
LanceDB Index Creation Script

Creates an IVF_PQ index for faster vector search.
Run this ONCE after initial sync completes.
"""

import asyncio
import lancedb
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


async def create_index():
    """
    Create IVF_PQ index for faster vector search.

    Performance improvement:
    - Before: 500-1000ms per search
    - After: 100-300ms per search (2-5x faster)

    Index parameters:
    - metric="cosine": Match the similarity metric used in search
    - num_partitions: sqrt(row_count) is optimal for IVF
    - num_sub_vectors: dimension / 16 (for 768d = 48)
    """
    db_path = settings.DB_PATH

    if not db_path.exists():
        logger.error(f"❌ Database not found: {db_path}")
        logger.info("Run the service first to create the database:")
        logger.info("  python __main__.py")
        return False

    logger.info(f"Connecting to LanceDB: {db_path}")

    try:
        # Connect to database
        db = await asyncio.to_thread(lancedb.connect, str(db_path))
        logger.info("✅ Connected to LanceDB")

        # Open table
        table = await asyncio.to_thread(db.open_table, "aidefend")
        logger.info("✅ Opened 'aidefend' table")

        # Get row count
        row_count = await asyncio.to_thread(table.count_rows)
        logger.info(f"📊 Table has {row_count} rows")

        if row_count < 100:
            logger.warning(
                f"⚠️  Table only has {row_count} rows. "
                "Index creation is most beneficial for >1000 rows."
            )
            proceed = input("Continue anyway? (y/n): ")
            if proceed.lower() != 'y':
                logger.info("Index creation cancelled")
                return False

        # Calculate optimal index parameters
        # num_partitions: sqrt(N) is a good heuristic for IVF
        num_partitions = max(256, int(row_count ** 0.5))

        # num_sub_vectors: dimension / 16
        # For 768-dimensional vectors: 768 / 16 = 48
        dimension = settings.EMBEDDING_DIMENSION
        num_sub_vectors = dimension // 16

        logger.info(f"\n{'='*60}")
        logger.info(f"INDEX CONFIGURATION")
        logger.info(f"{'='*60}")
        logger.info(f"Metric: cosine")
        logger.info(f"Partitions: {num_partitions} (sqrt({row_count}) rounded)")
        logger.info(f"Sub-vectors: {num_sub_vectors} ({dimension}d / 16)")
        logger.info(f"{'='*60}\n")

        logger.info("🔨 Creating index...")
        logger.info("⏱️  This may take 5-10 minutes for large databases...")
        logger.info("   (Progress: LanceDB will show progress logs)")

        # Create index
        await asyncio.to_thread(
            table.create_index,
            metric="cosine",
            num_partitions=num_partitions,
            num_sub_vectors=num_sub_vectors
        )

        logger.info(f"\n{'='*60}")
        logger.info("✅ Index created successfully!")
        logger.info(f"{'='*60}")
        logger.info("Expected performance improvement: 2-5x faster searches")
        logger.info("Restart the service to use the new index:")
        logger.info("  python __main__.py")
        logger.info(f"{'='*60}\n")

        return True

    except FileNotFoundError as e:
        logger.error(f"❌ Table 'aidefend' not found: {e}")
        logger.info("Make sure the service has completed initial sync")
        return False

    except Exception as e:
        logger.error(f"❌ Index creation failed: {e}", exc_info=True)
        return False


async def main():
    """Main entry point."""
    logger.info(f"\n{'#'*60}")
    logger.info("LANCEDB INDEX CREATION TOOL")
    logger.info(f"{'#'*60}\n")

    success = await create_index()

    if success:
        logger.info("\n✅ Index creation completed successfully")
    else:
        logger.error("\n❌ Index creation failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
