# Checkers

A simple checkers game. I started this project with a fellow programmer at
Hacker School to explore and gain experience with pygame and software
engineering tools for the python ecosystem, like nosetest and travis-ci. It
became a motif for learning a number of other things.

I used this and my [nodejs-based web
application](https://github.com/batkinson/checkers-html) to make a bootable game
server with a raspberry pi. The pygame-based clients locate the game server
using avahi/zeroconf by default. I also rewrote the game server to be
single-threaded so it runs more efficiently under CPython.

![Game Screen](images/screenshot.png?raw=true)

## Requirements

To run this program, you'll need:

  * A working Python 2 environment
  * PyGame (for the game client-only)

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
./unthreaded_server.py --zeroconf
```

Once the game server is started you can play games by running:

```
cd $CHECKERS/checkers
./checkers.py
```

By default, the server starts on a random port. By specifying --zeroconf, the
server publishes itself with an embedded zeroconf server. The pygame client will
search for a server over zeroconf by default, so it should find it as long as
you are running them from the same host. For clients to reliably find your
server from other hosts, you should specify the --interface option when starting
your server.
