import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase


# Try to load local .env only when running locally
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def get_config_value(name, default=""):
    """
    Works in both:
    - Local: reads from .env
    - Streamlit Cloud: reads from st.secrets
    """
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass

    return os.getenv(name, default)


NEO4J_URI = get_config_value("NEO4J_URI", "").strip()
NEO4J_USERNAME = get_config_value("NEO4J_USERNAME", "").strip()
NEO4J_PASSWORD = get_config_value("NEO4J_PASSWORD", "").strip()
NEO4J_DATABASE = get_config_value("NEO4J_DATABASE", "neo4j").strip()


if not NEO4J_URI or not NEO4J_USERNAME or not NEO4J_PASSWORD:
    raise ValueError("Neo4j connection details missing. Check .env or Streamlit secrets.")


class Neo4jManager:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def run_cypher(self, query, parameters=None):
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]