Packaging (single-file demo)

1) Install packaging dependency:
   pip install -r requirements-packaging.txt

2) Build a single-file executable:
   pyinstaller --onefile --noconsole --add-data "data/sample_docs;data/sample_docs" --add-data "data/user_docs;data/user_docs" app.py

Notes:
- On Linux/macOS, replace the data separator ';' with ':'.
- The output binary will be in dist/app.
- If you want the icon or custom name, pass --name and --icon.
