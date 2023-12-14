from setuptools import setup, find_packages

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='ducky-me',
    version='1.0.0',
    description='',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/ParthSareen/ducky',
    author='Parth Sareen',
    author_email='psareen@uwaterloo.ca',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'transformers',
    ],
    entry_points={
        'console_scripts': [
            'ducky=ducky:ducky',
        ],
    },
)