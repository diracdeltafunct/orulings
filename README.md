# ScoutsCode

A Django web application for browsing Riftbound card game rules and cards. Features comprehensive rules and tournament rules with full-text search, card search with filtering, and an annotation system for authenticated users.

## Features

- **Core Rules** — All comprehensive rules on a single page with anchor navigation and a sticky table of contents
- **Tournament Rules** — Hierarchical browsing of tournament rule sections
- **Rule Search** — Full-text search across both rule sets, including annotations
- **Card Search** — Filter cards by name, type, set, rarity, domain, energy, power, ability, and errata status
- **Annotations** — Authenticated users can add rich-text annotations to any rule section via a Quill editor
- **Dark/Light Mode** — Theme toggle with localStorage persistence

## Getting Started

### Prerequisites

- Python 3.10+
- Django 6.x

### Installation

1. Clone the repository:

   ```
   git clone https://github.com/diracdeltafunct/orulings.git
   cd orulings
   ```

2. Create and activate a virtual environment:

   ```
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   ```

3. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

4. Configure environment variables:

   Copy `.env-sample` to `.env` and fill in your values.

5. Apply migrations:

   ```
   python manage.py migrate
   ```

6. Import rules data:

   ```
   python manage.py import_rules
   ```

7. Run the development server:

   ```
   python manage.py runserver
   ```

## Restarting in Production

To restart the application on the server:

```
sudo systemctl restart gunicorn
```

## Project Structure

- `post/` — Main app: models, views, and templates for rules and cards
- `blog/` — Django project settings and URL configuration
- `static/css/` — Custom styles (Bootstrap 5.3 + `style.css`)
- `staticfiles/crsections/` — Comprehensive rules JSON source files
- `staticfiles/trsections_january_2026/` — Tournament rules JSON source files

## License

This project is licensed under the [MIT License](LICENSE).
