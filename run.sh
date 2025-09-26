#!/bin/bash

sudo docker build . -t nabu-server:latest
sudo docker run -v /.cache:/.cache -v .env:/.env -v $HOME/.cache/:/root/.cache --network host nabu-server:latest
