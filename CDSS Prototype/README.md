# CDSS Prototype

This folder contains the source code and supporting files for the developed CDSS prototype, excluding separately installed services and files that cannot be shared due to licensing or security restrictions.

## Included Components

| Component | Description |
|---|---|
| `cdss-frontend/` | Godot application containing the shared practitioner-patient interface, 3D visualization, and interactive features. |
| `cdss_core/` | Python backend responsible for case processing, treatment evaluation, and knowledge retrieval, including the SQLite knowledge database. |
| `fhir_adapter/` | FHIR integration layer for exchanging clinical information with OpenEMR. |
| `bridge/` | Java bridge connecting the Python backend to the GDL2 rule engine. |
| `ruleset/` | GDL2 clinical rules used to evaluate prosthodontic treatment options. |
| `gdl_runtime/` | Supporting runtime libraries for executing the GDL2 rules. |

The folder also includes configuration examples and scripts used to launch and test the prototype.

## External Setup Dependencies

The following dependencies must be installed or configured separately.

| Dependency | Setup |
|---|---|
| **Godot Engine 4.7.2** | Download the [Windows 64-bit standard version](https://godotengine.org/download/archive/4.7.2-stable/) and place `Godot_v4.7.2-stable_win64.exe` inside a `Godot/` folder at the project root. |
| **Python** | Create the `.venv/` environment and install the dependencies listed in `requirements.txt`. |
| **Java Runtime** | Required for the Java bridge and GDL2 rule evaluation. |
| **OpenEMR** | Installed and configured separately through Docker, including SMART on FHIR application registration and the required clinical data structures. |
| **SNOMED CT** | Obtain an individual Affiliate License through the [SNOMED CT licensing and distribution service](https://mlds.ihtsdotools.org/de), download the appropriate terminology release, and configure its integration into MariaDB. The licensed terminology database is not distributed with this repository. |
| **Local configuration** | Environment variables, credentials, and certificates must be configured locally. These files are not included in the repository. |

The supplied launch scripts assume the expected local folder structure and configuration, but can be modified to accommodate different installation paths and local setups.

## OpenEMR Integration

The original OpenEMR installation is not included in this repository. To reproduce the integration, users need to:

1. **Install and configure OpenEMR**, including its FHIR API and the dental odontogram and HbA1c forms used to record clinical findings.
2. **Obtain SNOMED CT under their own license** and import the required terminology into MariaDB.
3. **Provide read-only MariaDB access to the included FHIR adapter.** The adapter reads the relevant OpenEMR clinical tables directly and is already implemented in this repository. Its database access is separate from SMART on FHIR authorization.
4. **Register the CDSS as a SMART on FHIR application in OpenEMR**, specifying the launch URL, redirect URL, and required FHIR read permissions.
5. **Update the local configuration** with the new SMART client ID, client secret, issuer, redirect URI, certificate path, and MariaDB connection credentials.

The developed code already implements SMART authentication, patient and encounter retrieval, FHIR data processing, and GDL2 rule evaluation. Once the external environment is configured, the CDSS can evaluate patient-specific findings, display treatment options and cautions, and provide supporting explanations through its shared interface.

**The integration is read-only.** Practitioners can edit and reevaluate clinical findings within the CDSS working case, but these changes are not written back to OpenEMR.
