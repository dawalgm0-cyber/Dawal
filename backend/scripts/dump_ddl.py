"""Compile every model to Postgres DDL WITHOUT a live database, using a mock
engine. Validates that all types/constraints are valid for postgresql:16."""

from sqlalchemy import create_mock_engine
from sqlalchemy.schema import CreateTable

from app.models import Base


def dump(sql, *args, **kwargs):
    print(str(sql.compile(dialect=engine.dialect)).strip() + ";\n")


engine = create_mock_engine("postgresql+psycopg://", dump)

tables = Base.metadata.sorted_tables
print(f"-- DAWAL schema: {len(tables)} tables, Postgres dialect\n")
for table in tables:
    print(str(CreateTable(table).compile(dialect=engine.dialect)).strip() + ";\n")
