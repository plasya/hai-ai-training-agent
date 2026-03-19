import pandas as pd
from sqlalchemy import create_engine

DB_URL = "postgresql+psycopg2://app:app@localhost:5432/health"

engine = create_engine(DB_URL)

def query(sql):
    return pd.read_sql(sql, engine)