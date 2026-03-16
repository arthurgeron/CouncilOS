#!/bin/bash
source /Users/zed/crewai-env/bin/activate
cd /Users/zed/Projects/Personal/council
exec uvicorn api:app --host 0.0.0.0 --port 8000
