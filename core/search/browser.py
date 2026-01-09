import requests

def visit_page(url: str, max_chars: int = 25000, include_header: bool = True) -> str:
    """
    Visits a web page and extracts the main text content (no ads/menus).
    """
    print(f"Browsing: {url}...")
    try:
        try:
            import trafilatura
        except ImportError as e:
            message = (
                "[Browser Error: Missing optional dependency for trafilatura. "
                "Install `lxml_html_clean` or `lxml[html_clean]` to fix.]"
            )
            return message

        # Download HTML
        downloaded = trafilatura.fetch_url(url)
        
        if not downloaded:
            # fallback for some sites that block default user agents
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; HalaAI/1.0)'}
            response = requests.get(url, headers=headers, timeout=10)
            downloaded = response.text

        # extract Main Text
        # include_comments=False removes user comments
        # include_tables=True keeps data tables
        text = trafilatura.extract(
            downloaded, 
            include_comments=False, 
            include_tables=True,
            no_fallback=False
        )
        
        if not text:
            return "[Error: Page loaded but no readable text found. It might be Javascript-heavy.]"
            
        # truncate
        content = text[:max_chars]
        if include_header:
            return f"--- CONTENT FROM {url} ---\n{content}\n[...text truncated...]"
        return content
        
    except Exception as e:
        return f"[Browser Error: {e}]"
    
if __name__ == "__main__":
    print(visit_page("https://www.prnewswire.com/news-releases/novo-nordisks-wegovy-pill-the-first-and-only-oral-glp-1-for-weight-loss-in-adults-now-broadly-available-across-america-302652205.html"))
