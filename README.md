# TronClassSurvey
Automatically fill out all the surveys

## Installation
1. Clone the repository:
```bash
git clone https://github.com/ZerolBozi/TronClassSurvey.git
cd TronClassSurvey
```

2. Install Python packages:
```bash
pip install -r requirements.txt
```

3. Create environment file:
   - Create a new .env file or copy .env.example to .env in the project root directory
   - Add your NFU account credentials to the .env file:
```plaintext
ACCOUNT=your_account
PASSWORD=your_password
```

4. Run the script:
```bash
python TronClassSurvey.py
```

## Configuration
You can customize the survey responses by modifying study_answers.json. The tool supports different answer patterns