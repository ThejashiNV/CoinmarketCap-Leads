# CoinMarketCap Leads Extraction

A Python-based web scraping project that extracts lead information from CoinMarketCap and stores the results in CSV format for further analysis and outreach.

## Features

- Extracts company and lead details from CoinMarketCap
- Saves structured data to CSV files
- Configurable settings through `config.py`
- Modular and easy-to-maintain code

## Project Structure

```
CoinmarketCap-Leads/
├── main.py          # Main script to run the scraper
├── config.py        # Configuration settings
├── output/          # Generated CSV output files
├── __pycache__/     # Python cache files
└── README.md        # Project documentation
```

## Requirements

- Python 3.9 or above
- Required Python packages (install using `requirements.txt` if available)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/ThejashiNV/CoinmarketCap-Leads.git
cd CoinmarketCap-Leads
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
```

On Windows:

```bash
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

> If a `requirements.txt` file is not available, install the required packages manually.

## Usage

Run the scraper using:

```bash
python main.py
```

The extracted data will be saved in the `output/` folder as CSV files.

## Sample Output

The generated CSV may contain fields such as:

- Company Name
- Website
- Category
- Description
- Contact Information

## Configuration

Update the `config.py` file to customize scraper settings such as:

- Target URLs
- Output file names
- Scraping parameters

## Repository

https://github.com/ThejashiNV/CoinmarketCap-Leads

## Author

Thejashri Natarajan
