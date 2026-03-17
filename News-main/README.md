# News Intelligence

Streamlit app + CLI for news intelligence, summaries, and report generation.

## Structure
- `streamlit_app.py`: Streamlit entrypoint for GitHub/Streamlit deployment
- `cli.py`: CLI runner
- `news_app/`: application package
- `assets/template.pptx`: PPT template

## Streamlit (GitHub deploy)
1. Push this repo to GitHub.
2. In Streamlit Cloud, select this repo and set the main file to `streamlit_app.py`.
3. Configure Secrets in Streamlit Settings:
   - `DEEPSEEK_API_KEY`
   - `TAVILY_API_KEY`
   - `JINA_API_KEY` (optional)
   - `GITHUB_TOKEN` (optional, for memory)
   - `GIST_ID` (optional, for memory)

## Local run
```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## CLI
```
python cli.py
```
