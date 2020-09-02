#!/usr/bin/python3

import argparse
import datetime
import json
import matplotlib.pyplot as plt
import matplotlib.dates as dates
import os
import statistics
import subprocess
import sys
import time
import tinydb
import tweepy

THISDIR = os.path.dirname(os.path.abspath(__file__))
TINYDB = os.path.join(THISDIR, "db.json")
CFG = os.path.join(THISDIR, "cfg")
PLOTPNG = os.path.join(THISDIR, "plot.png")
NOW = time.time()

def parseargs():
    parser = argparse.ArgumentParser(description='@plutor_wifi tweet bot')
    parser.add_argument('--force_tweet', action='store_true')
    parser.add_argument('--only_test', action='store_true')
    parser.add_argument('--skip_test', action='store_true')
    return parser.parse_args()

class PlutorWifi(object):

    def __init__(self):
        # Load config
        with open(CFG) as f:
            data = f.read()
            self.cfg = json.loads(data)

        # Load recent history
        self.db = tinydb.TinyDB(TINYDB)
        Rec = tinydb.Query()
        self.hist = self.db.search(Rec.timestamp > NOW - 24*60*60)

        # Setup Twitter API
        auth = tweepy.OAuthHandler(self.cfg['api_key'], self.cfg['api_secret'],
                                   'https://oauthdebugger.com/debug')
        if ('oauth_token' not in self.cfg or 'oauth_verifier' not in self.cfg or
            not self.cfg['oauth_token'] or not self.cfg['oauth_verifier']):
            print('Visit', auth.get_authorization_url(), 'and grant plutor_wifi '
                  'access.')
            print('Then, add the values into', CFG, 'as follows:')
            print('  "oauth_token": "(value of oauth_token)",')
            print('  "oauth_verifier": "(value of oauth_verifier)"\n}')
            sys.exit(1)
        auth.set_access_token(self.cfg['oauth_token'], self.cfg['oauth_verifier'])
        self.api = tweepy.API(auth)

    def run_speedtests(self):
        """Runs all configured speedtests.

        returns:
            a hash of speedtest names to (down Mbps, up Mbps, ping Mbps) data
        """
        rv = {}
        speedtest = self.run_ookla()
        if speedtest:
            rv['speedtest'] = speedtest
        fastcom = self.run_fastcom()
        if fastcom:
            rv['fastcom'] = fastcom
        mlab = self.run_mlabndt()
        if mlab:
            rv['mlab'] = mlab
        chromedl = self.run_chromedl()
        if chromedl:
            rv['chromedl'] = chromedl
        return rv

    def run_ookla(self):
        """Runs Ookla speedtest.net

        returns:
            (down Mbps, up Mbps, ping Mbps)
        """
        print("Running ookla speedtest.net")
        cp = subprocess.run(['speedtest-cli', '--simple'], stdout=subprocess.PIPE)
        print(cp)
        if cp.returncode != 0:
            print('Bad return code %d' % cp.returncode)
            return None
        down = up = ping = -1
        for line in cp.stdout.split(b"\n"):
            try:
                type, val, unit = line.split()
                if type == b'Download:':
                    down = float(val)
                elif type == b'Upload:':
                    up = float(val)
                elif type == b'Ping:':
                    ping = float(val)
            except:
                next
        return (down, up, ping)

    def run_fastcom(self):
        """Runs Fast.com test

        returns:
            (down Mbps, None, None)
        """
        print("Running fast.com")
        cp = subprocess.run(['fast-cli', '-s'], stdout=subprocess.PIPE)
        print(cp)
        if cp.returncode != 0:
            print('Bad return code %d' % cp.returncode)
            return None
        val, unit = cp.stdout.split()
        return (float(val), None, None)

    def run_mlabndt(self):
        """Runs M-Lab NDT test

        Will only run a maximum of once per hour.

        returns:
            (down Mbps, up Mbps, ping Mbps)
        """
        if not self.should_mlabndt(60*60):
            print("Skipping M-Lab NDT")
            return
        print("Running M-Lab NDT")
        cp = subprocess.run(['ndt7-client', '-quiet', '-format=json'], stdout=subprocess.PIPE)
        print(cp)
        if cp.returncode != 0:
            print('Bad return code ', cp.returncode)
            return None
        data = json.loads(cp.stdout.decode("utf-8")) 
        return (data['Download']['Value'], data['Upload']['Value'], data['MinRTT']['Value'])

    def should_mlabndt(self, max_age_secs):
        for rec in self.hist:
            if 'mlab' in rec['data'] and rec['timestamp'] > NOW - max_age_secs:
                return False
        return True

    def run_chromedl(self):
        print("Running Chrome download")
        cp = subprocess.run(['curl', 'https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb', '-o', '/dev/null', '-s', '-w', '%{speed_download}'], stdout=subprocess.PIPE)
        print(cp)
        if cp.returncode != 0:
            print('Bad return code ', cp.returncode)
            return None
        bytes_persec = float(cp.stdout)
        return (bytes_persec * 8 / 1024 / 1024, None, None)

    # ========================

    def save_data(self, data, do_tweet):
        row = {'data': data, 'tweeted': do_tweet, 'timestamp': NOW}
        self.db.insert(row)
        self.hist.append(row)

    def generate_graph(self):
        """Returns med_down, med_up."""
        print("Creating graph")
        # Define data
        xs = [[], [], [], [], [], []]
        ys = [[], [], [], [], [], []]
        for run in self.hist:
            stamp = datetime.datetime.fromtimestamp(run['timestamp'])
            if 'speedtest' in run['data']:
                ys[0].append(run['data']['speedtest'][0])
                xs[0].append(stamp)
                ys[4].append(run['data']['speedtest'][1])
                xs[4].append(stamp)
            if 'fastcom' in run['data']:
                ys[1].append(run['data']['fastcom'][0])
                xs[1].append(stamp)
            if 'mlab' in run['data']:
                ys[2].append(run['data']['mlab'][0])
                xs[2].append(stamp)
                ys[5].append(run['data']['mlab'][1])
                xs[5].append(stamp)
            if 'chromedl' in run['data']:
                ys[3].append(run['data']['chromedl'][0])
                xs[3].append(stamp)

        med_down = statistics.median(filter(None, ys[0]+ys[1]+ys[2]))
        med_up = statistics.median(filter(None, ys[3]+ys[4]))

        # Plot data including options
        fig, ax = plt.subplots(figsize=(8, 4.4), sharex=True)
        ax.xaxis.set_major_formatter(dates.DateFormatter('%H:%M'))
        ax.minorticks_on()
        for n, x in enumerate(xs):
            ax.plot(x, ys[n])

        # Add plot details
        plt.ylabel('Mbps')
        plt.legend(['speedtest down', 'fast.com down', 'mlab down', 'chrome down',
                    'speedtest up', 'mlab up'])
        plt.style.use('fivethirtyeight')

        # Save the plot
        plt.savefig(PLOTPNG, dpi=100, bbox_inches='tight')
        plt.show()

        return med_down, med_up

    def tweet_history(self, max_age_secs):
        med_down, med_up = self.generate_graph()
        print("Tweeting graph")
        media = self.api.media_upload(PLOTPNG)
        self.api.update_status('Median speed: %.1f Mbps down / %.1f Mbps up' % (med_down, med_up),
                               media_ids=[media.media_id])

    def tweet_due(self, max_age_secs):
        for rec in self.hist:
            if rec['tweeted'] and rec['timestamp'] > NOW - max_age_secs:
                return False
        return True

def main():
    args = parseargs()
    p = PlutorWifi()

    do_tweet = (args.force_tweet or p.tweet_due(8*60*60)) and not args.only_test
    if not args.skip_test:
        data = p.run_speedtests()
        if data:
            p.save_data(data, do_tweet)
        
    if do_tweet:
        p.tweet_history(24*60*60)
    else:
        print("Skipping tweet")

main()

