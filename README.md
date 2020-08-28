# plutor_wifi

https://twitter.com/plutor_wifi

## Dependencies

mLab NDT client: https://github.com/m-lab/ndt7-client-go

speedtest-cli: https://github.com/sivel/speedtest-cli

fast-cli: https://github.com/gesquive/fast-cli

matplotlib for plotting: https://problemsolvingwithpython.com/06-Plotting-with-Matplotlib/06.13-Plot-Styles/

tweepy for tweeting: https://www.tweepy.org/


## Setup

```
$ sudo pip3 install numpy matplotlib tweepy tinydb speedtest-cli

$ wget https://golang.org/dl/go1.15.linux-armv6l.tar.gz && sudo tar -C /usr/local -xzf go1.15.linux-armv6l.tar.gz && sudo ln -s /usr/local/go/bin/go /usr/bin/go

$ mkdir $HOME/go

$ GOPATH="$HOME/go"

$ go get -v github.com/m-lab/ndt7-client-go/cmd/ndt7-client && sudo ln -s $HOME/go/bin/ndt7-client /usr/bin

$ go get -v github.com/gesquive/fast-cli && sudo ln -s $HOME/go/bin/fast-cli /usr/bin
```

* Create a Twitter app, a new Twitter account, and do the somersaults to get the tokens.

* Put the tokens in a config file and create a crontab

