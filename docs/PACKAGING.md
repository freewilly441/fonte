Packaging (single-file demo)

1) Install packaging dependency:
   pip install -r requirements-packaging.txt

2) Build a single-file executable:
   pyinstaller --onefile --noconsole --collect-data sv_ttk --add-data "data/sample_docs;data/sample_docs" --add-data "data/user_docs;data/user_docs" app.py

Notes:
- On Linux/macOS, replace the data separator ';' with ':'.
- `--collect-data sv_ttk` bundles the Sun Valley theme assets for modern ttk styling.
- The output binary will be in dist/app.
- If you want the icon or custom name, pass --name and --icon.

Mobile Linux / Android flashable package

1) Build the mobile archive:
   ./scripts/build_android_flashable.sh

2) Copy `dist/fonte-mobile-flashable.zip` to the device and unzip.

3) In Termux, run installer from the unzipped project directory:
   bash mobile/install_termux.sh

4) Run the headless mobile CLI:
   bash mobile/run_mobile.sh init
   bash mobile/run_mobile.sh ingest data/user_docs --workers 4
   bash mobile/run_mobile.sh ask "Your question here"
