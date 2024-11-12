from setuptools import setup, find_packages

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='rubber-ducky',
    version='1.1.2',
    description='AI Companion for Pair Programming',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/ParthSareen/ducky',
    author='Parth Sareen',
    author_email='psareen@uwaterloo.ca',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'ollama',
    ],
    entry_points={
        'console_scripts': [
            'ducky=ducky.ducky:main',
        ],
    },
)