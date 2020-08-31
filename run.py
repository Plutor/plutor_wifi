#!/usr/bin/python3

import argparse
import datetime
import json
import matplotlib.pyplot as plt
import os
import statistics
import subprocess
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

        returns:
            (down Mbps, up Mbps, ping Mbps)
        """
        print("Running M-Lab NDT")
        cp = subprocess.run(['ndt7-client', '-quiet', '-format=json'], stdout=subprocess.PIPE)
        print(cp)
        if cp.returncode != 0:
            print('Bad return code ', cp.returncode)
            return None
        data = json.loads(cp.stdout.decode("utf-8")) 
        return (data['Download']['Value'], data['Upload']['Value'], data['MinRTT']['Value'])


    # ========================

    def save_data(self, data, do_tweet):
        row = {'data': data, 'tweeted': do_tweet, 'timestamp': NOW}
        self.db.insert(row)
        self.hist.append(row)

    def generate_graph(self):
        """Returns med_down, med_up."""
        print("Creating graph")
        # Define data
        x = []
        ys = [[], [], [], [], []]
        for run in self.hist:
            x.append(datetime.datetime.fromtimestamp(run['timestamp']))
            if 'speedtest' in run['data']:
                ys[0].append(run['data']['speedtest'][0])
                ys[3].append(run['data']['speedtest'][1])
            else:
                ys[0].append(None)
                ys[3].append(None)
            if 'fastcom' in run['data']:
                ys[1].append(run['data']['fastcom'][0])
            else:
                ys[1].append(None)
            if 'mlab' in run['data']:
                ys[2].append(run['data']['mlab'][0])
                ys[4].append(run['data']['mlab'][1])
            else:
                ys[2].append(None)
                ys[4].append(None)

        med_down = statistics.median(filter(None, ys[0]+ys[1]+ys[2]))
        med_up = statistics.median(filter(None, ys[3]+ys[4]))

        # Plot data including options
        fig, ax = plt.subplots(figsize=(8, 4.4))
        for y in ys:
            ax.plot(x, y)

        # Add plot details
        plt.ylabel('Mbps')
        plt.legend(['speedtest down', 'fast.com down', 'mlab down', 'speedtest up', 'mlab up'])
        plt.style.use('fivethirtyeight')

        # Save the plot
        plt.savefig(PLOTPNG, dpi=100, bbox_inches='tight')
        plt.show()

        return med_down, med_up

    def tweet_history(self, max_age_secs):
        auth = tweepy.OAuthHandler(self.cfg['api_key'], self.cfg['api_secret'])
        auth.set_access_token(self.cfg['access_token'], self.cfg['access_token_secret'])
        api = tweepy.API(auth)
        med_down, med_up = self.generate_graph()
        print("Tweeting graph")
        media = api.media_upload(PLOTPNG)
        api.update_status('Median speed: %.1f Mbps down / %.1f Mbps up' % (med_down, med_up), media_ids=[media.media_id])

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

