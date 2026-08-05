from database.models import create_tables
from database.database_manager import DatabaseManager


# Create all tables when imported
create_tables()

# Global database manager used by the whole bot
database = DatabaseManager()