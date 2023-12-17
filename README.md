# rubber ducky

## tl;dr
- `pip install rubber-ducky`
- Install ollama
- `ollama run codellama` (first time and then you can just have application in background)
- There are probably other dependencies which I forgot to put in setup.py sorry in advance.
- Run with `ducky -f <file path>`

## Why did I make this 

I wrote ducky because I annoy engineers too much and I needed to talk someone through my code quickly and validate my approach. Maybe this is why I'm not a senior engineer.

Since I can't dump all my code to GPT and make it tell me I know how to code, I decided to build something for quick iteration. All. Local. I also didn't want to get fired by leaking all our data. Not again.

## Dependencies
Bless the folks at Ollama cause they have been carrying my recent projects.

This project is currently only supported on Mac and Linux cause Ollama is a dependency.
You will need Ollama installed on your machine. The model I use for this project is `codellama`. 

For the first installation you can run `ollama run codellama` and it should pull the necessary binaries for you. Ollama is also great because it'll spin up a server which can run in the background and can even do automatic model switching as long as you have it installed.

## Usage

Install through [pypi](https://pypi.org/project/rubber-ducky/):

`pip install rubber-ducky` .

### Simple run
`ducky`

### To use additional options:

`ducky --file <path> --prompt <prompt> --directory <directory> --chain --model <model>`

Where:
- `--prompt` or `-p`: Custom prompt to be used
- `--file` or `-f`: The file to be processed
- `--directory` or `-d`: The directory to be processed
- `--chain` or `-c`: Chain the output of the previous command to the next command
- `--model` or `-m`: The model to be used (default is "codellama")


## Example output
![Screenshot of ducky](image.png)