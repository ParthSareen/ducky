# ducky

Ducky Project
Overview
Ducky is a Python project that uses the ChatOllama language model from the langchain_core package. It's designed to generate responses based on a given prompt.
Installation
To install the necessary dependencies, you'll need to create a virtual environment and install the packages listed in the requirements.txt file.


``` python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Usage
To use Ducky, you'll need to run the ducky.py script with a prompt as an argument. The script will pass the prompt to the ChatOllama instance and print the generated response.

`python ducky.py --prompt "Your prompt here"`
