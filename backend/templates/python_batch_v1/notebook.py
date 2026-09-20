# Databricks notebook source
"""Synthetic output preview. Workspace execution requires separate authorization."""
import json
from src.__PACKAGE__.batch import summarize

print(json.dumps(summarize(__ROWS__), sort_keys=True))
