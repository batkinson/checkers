# Checkers

It's just what it sounds like: a simple checkers game. I started this project
with a fellow Hacker School attendee to explore and gain experience with pygame
and python software development tools like nosetest and travis-ci.

[Game Screen](images/screenshot.png?raw=true)

## Requirements

To run this program, you'll need:

  * A working Python 2 environment
  * PyGame

## Setup

To run the program, you just need to install the dependencies. This should be
as simple as running:

```
pip install -r requirements.txt
```

However, you likely will not be able to install pygame through pip. Under Ubuntu
you should just be able to install pygame through apt:

```
sudo apt-get install python-pygame
```
Then you can re-run the pip install command above to complete the installation.

## Running

Starting the game server is as simple as running:

```
cd $CHECKERS_HOME/checkers
./netserver.py
```

Once the game server is started you can play games by running:

```
cd $CHECKERS/checkers
./checkers.py
```

By default, the server starts on port 5000 and the game clients try to connect to a game server at 127.0.0.1 on port 
5000.
