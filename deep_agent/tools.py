import traceback
from tavily import TavilyClient
from typing import Literal, Dict, Any
import requests
import os
import time

import yaml

if "TAVILY_API_KEY" in os.environ:
    tavily_client = TavilyClient(
        api_key=os.getenv("TAVILY_API_KEY"),
    )
else:
    tavily_client = None

VERIFIER_URL = os.getenv("VERIFIER_URL", "http://localhost:5000")


def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    if tavily_client is None:
        return {"error": "Internet search is unavailable"}
    return tavily_client.search(
        query=query,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
    )


def get_catalog() -> Dict[str, Any]:
    """Return the current action/validator catalog (parsed YAML)."""
    path = os.getenv(
        "CATALOG_PATH",
        os.path.join(os.path.dirname(__file__), "../codex_verifier/catalog.yaml"),
    )
    with open(path, "r") as f:
        x = yaml.safe_load(f)
        print("catalog:", x)
        return x
