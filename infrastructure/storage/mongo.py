"""MongoDB storage handler."""

import logging
from typing import Any, Dict, List, Optional, Union

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from config.settings import config

logger = logging.getLogger(__name__)


class MongoHandler:
    """MongoDB handler with context manager support."""

    def __init__(self, db_name: Optional[str] = None):
        """Initialize MongoDB handler.

        Args:
            db_name: Database name
        """
        self.db_name = db_name or config.MONGO_DB_NAME
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def _connect(self) -> None:
        """Establish connection to MongoDB."""
        if self._client is None:
            self._client = MongoClient(config.MONGO_URL)
            self._db = self._client[self.db_name]
            logger.debug(f"Connected to MongoDB: {self.db_name}")

    def get_collection(self, name: str) -> Collection:
        """Get a collection.

        Args:
            name: Collection name

        Returns:
            MongoDB collection
        """
        self._connect()
        return self._db[name]

    def find_one(
        self,
        collection: str,
        query: Dict[str, Any],
        projection: Optional[Dict[str, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find a single document.

        Args:
            collection: Collection name
            query: Query filter
            projection: Fields to include/exclude

        Returns:
            Document or None
        """
        coll = self.get_collection(collection)
        return coll.find_one(query, projection)

    def find_many(
        self,
        collection: str,
        query: Dict[str, Any],
        projection: Optional[Dict[str, int]] = None,
        sort: Optional[str] = None,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents.

        Args:
            collection: Collection name
            query: Query filter
            projection: Fields to include/exclude
            sort: Sort field (prefix with '-' for descending)
            limit: Maximum documents to return

        Returns:
            List of documents
        """
        coll = self.get_collection(collection)
        cursor = coll.find(query, projection)

        if sort:
            if sort.startswith("-"):
                cursor = cursor.sort(sort[1:], -1)
            else:
                cursor = cursor.sort(sort, 1)

        if limit > 0:
            cursor = cursor.limit(limit)

        return list(cursor)

    def update_one(
        self,
        collection: str,
        query: Dict[str, Any],
        update_data: Dict[str, Any],
    ) -> int:
        """Update a single document.

        Args:
            collection: Collection name
            query: Query filter
            update_data: Data to update

        Returns:
            Number of modified documents
        """
        coll = self.get_collection(collection)
        result = coll.update_one(query, {"$set": update_data})
        return result.modified_count

    def insert_one(self, collection: str, document: Dict[str, Any]) -> str:
        """Insert a document.

        Args:
            collection: Collection name
            document: Document to insert

        Returns:
            Inserted document ID
        """
        coll = self.get_collection(collection)
        result = coll.insert_one(document)
        return str(result.inserted_id)

    @staticmethod
    def to_object_id(id_str: Union[str, ObjectId]) -> ObjectId:
        """Convert string to ObjectId.

        Args:
            id_str: ID string or ObjectId

        Returns:
            ObjectId instance
        """
        if isinstance(id_str, ObjectId):
            return id_str
        return ObjectId(id_str)

    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.debug("MongoDB connection closed")

    def __enter__(self) -> "MongoHandler":
        """Context manager entry."""
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
