# rubber ducky

## tl;dr
- `pip install rubber-ducky`
- Install ollama
- `ollama run codellama` (first time and then you can just have application in background)
- There are probably other dependencies which I forgot to put in setup.py sorry in advance.
- run with `ducky --file <path> --prompt (optional) <prompt to override>`

## Why did I make this 

I wrote ducky because I annoy engineers too much and I needed to talk someone through my code quickly and validate my approach. Maybe this is why I'm not a senior engineer.

Since I can't dump all my code to GPT and make it tell me I know how to code, I decided to build something for quick iteration. All. Local. I also didn't want to get fired by leaking all our data. Not again.

## Dependencies
Bless the folks at Ollama cause they have been carrying my recent projects.

This project is currently only supported on Mac and Linux cause Ollama is a dependency.
You will need Ollama installed on your machine. The model I use for this project is `codellama`. 

For the first installation you can run `ollama run codellama` and it should pull the necessary binaries for you. Ollama is also great because it'll spin up a server which can run in the background and can even do automatic model switching as long as you have it installed.

## Usage
Make sure you have the package installed. Easiest through [pypi](https://pypi.org/project/rubber-ducky/). 

`pip install rubber-ducky` also works.

To run:

`ducky --file <path> --prompt (optional) <prompt to override>`

I have yet to implement some methods so if you do something I don't say that's on you.
