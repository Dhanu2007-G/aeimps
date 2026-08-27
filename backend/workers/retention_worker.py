"""Data retention and archival worker."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Document, RetentionPolicy
from app.db.postgres import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def apply_retention_policies():
    """Apply retention policies to documents and audit logs."""
    async with async_session_factory() as db:
        # Get active retention policies
        result = await db.execute(
            select(RetentionPolicy).where(RetentionPolicy.is_active == True)
        )
        policies = result.scalars().all()
        
        for policy in policies:
            logger.info(f"Applying retention policy: {policy.name}")
            
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=policy.retention_days)
            
            if policy.resource_type == "document":
                # Archive/delete old documents
                stmt = select(Document).where(Document.created_at < cutoff_date)
                
                # Apply match criteria (e.g., specific tags)
                if policy.match_criteria.get("tags"):
                    stmt = stmt.where(Document.tags.contains(policy.match_criteria["tags"]))
                
                old_docs = await db.execute(stmt)
                for doc in old_docs.scalars():
                    if policy.archive_before_delete:
                        # Mark as archived (could move to cold storage)
                        doc.metadata_["archived"] = True
                        doc.metadata_["archived_at"] = datetime.now(timezone.utc).isoformat()
                    else:
                        await db.delete(doc)
                
                await db.commit()
                
            elif policy.resource_type == "audit_log":
                # Delete old audit logs
                stmt = delete(AuditLog).where(AuditLog.timestamp < cutoff_date)
                await db.execute(stmt)
                await db.commit()
            
            # Update last run time
            policy.last_run_at = datetime.now(timezone.utc)
            await db.commit()
            
        logger.info("Retention policies applied successfully")


async def main():
    """Run retention worker continuously."""
    while True:
        try:
            await apply_retention_policies()
        except Exception as e:
            logger.error(f"Retention worker error: {e}")
        
        # Run every 24 hours
        await asyncio.sleep(86400)


if __name__ == "__main__":
    asyncio.run(main())
