# Web Scraper Flask Application

This project is a Flask web application that provides a user interface for scraping data from social media platforms such as Instagram, Threads, and Facebook. It utilizes an existing web scraper functionality encapsulated in the `Scraper.py` file.

## Project Structure

```
webscraper-flask-app
├── app.py                # Entry point of the Flask application
├── scraper               # Directory containing the scraper logic
│   ├── __init__.py      # Marks the scraper directory as a Python package
│   └── Scraper.py       # Contains the web scraper functionality
├── templates             # Directory for HTML templates
│   └── index.html       # Main page template for user input and results
├── static                # Directory for static files (CSS, images, etc.)
│   └── style.css        # CSS styles for the web application
├── requirements.txt      # Lists the dependencies required for the project
└── README.md             # Documentation for the project
```

## Setup Instructions

1. **Clone the repository**:
   ```
   git clone <repository-url>
   cd webscraper-flask-app
   ```

2. **Create a virtual environment** (optional but recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install the required dependencies**:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. **Run the Flask application**:
   ```
   python app.py
   ```

2. **Access the application**:
   Open your web browser and go to `http://127.0.0.1:5000/`.

3. **Input User Data**:
   Use the provided interface to input the usernames of the social media accounts you wish to scrape.

4. **View Results**:
   After submitting the form, the application will trigger the scraping functionality and display the results.

## Dependencies

- Flask
- Selenium
- tqdm
- Other libraries as required by the scraper

## Contributing

Feel free to submit issues or pull requests if you have suggestions or improvements for the project.