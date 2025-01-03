from flask import Flask, render_template, request
from markupsafe import Markup
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from twitter_scraper import Tweet, Base
import re

app = Flask(__name__)

# Database setup
engine = create_engine('sqlite:///tweets.db')
Session = sessionmaker(bind=engine)

def url_to_link(text):
    """Convert URLs in text to HTML links."""
    # Pattern components:
    # 1. Protocol: https?:// 
    # 2. Domain: [^\s./]+ - domain start (no spaces, dots, or slashes)
    # 3. Subdomains: (?:\.[^\s./]+)* - zero or more subdomain parts
    # 4. Optional path: (?:/[^\s.]*[^\s.])?$ - optional forward slash followed by non-space, non-dot chars
    url_pattern = r'https?:\/\/[^\s\.\/]+(\.[^\s\.\/]+)*(\/[^\s…]*)?'
    
    def replace_url(match):
        url = match.group(0)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
    
    # Replace URLs with HTML links
    linked_text = re.sub(url_pattern, replace_url, text)
    return Markup(linked_text)

# Register the custom filter
app.jinja_env.filters['urlize'] = url_to_link

@app.route('/')
def index():
    session = Session()
    search_term = request.args.get('search', '').strip()
    
    # Base query
    query = session.query(Tweet).order_by(desc(Tweet.timestamp))
    
    # Apply search if term provided
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(Tweet.text.ilike(search_pattern) | Tweet.handle.ilike(search_pattern))
    
    tweets = query.all()
    session.close()
    
    return render_template('index.html', tweets=tweets, search_term=search_term)

if __name__ == '__main__':
    app.run(debug=True) 