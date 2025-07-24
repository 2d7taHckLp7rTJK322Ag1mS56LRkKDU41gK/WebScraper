from flask import Flask, render_template, request, redirect, url_for, flash
from scraper.Scraper import InstagramScraper, ThreadsScraper, FacebookScraper
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this to a random secret key

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    platform = request.form.get('platform')
    user = request.form.get('user')
    list_user = request.form.get('list_user')

    if not platform or (not user and not list_user):
        flash('Please provide a platform and either a user or a list of users.')
        return redirect(url_for('index'))

    scraper = None
    try:
        if platform == 'instagram':
            scraper = InstagramScraper(headless=True)
        elif platform == 'threads':
            scraper = ThreadsScraper(headless=True)
        elif platform == 'facebook':
            scraper = FacebookScraper(headless=True)

        if list_user:
            with open(list_user, 'r') as f:
                users = f.read().splitlines()
            scraper.scrape_users(users)
        else:
            scraper.scrape_users([user])

        flash('Scraping completed successfully!')
    except Exception as e:
        flash(f'An error occurred: {e}')
    finally:
        if scraper:
            scraper.close()

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)