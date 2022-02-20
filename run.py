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
COLORS = ['r', 'g', 'b', 'c']


def parseargs():
    parser = argparse.ArgumentParser(description='@plutor_wifi tweet bot')
    parser.add_argument('--force_tweet', action='store_true')
    parser.add_argument('--only_test', action='store_true')
    parser.add_argument('--skip_test', action='store_true')
    parser.add_argument('--dry_run', action='store_true')
    return parser.parse_args()


class PlutorWifi(object):

    def __init__(self):
        # Load config
        self.read_cfg()

        # Load recent history
        self.db = tinydb.TinyDB(TINYDB)
        Rec = tinydb.Query()
        self.hist = self.db.search(Rec.timestamp > NOW - 24*60*60)

    def read_cfg(self):
        with open(CFG) as f:
            data = f.read()
            self.cfg = json.loads(data)

    def write_cfg(self):
        with open(CFG, 'w') as f:
            json.dump(self.cfg, f, indent=4)

    def auth(self):
        # Setup Twitter API
        auth = tweepy.OAuthHandler(self.cfg['api_key'], self.cfg['api_secret'],
                                   'https://oauthdebugger.com/debug')

        if ('request_token' not in self.cfg or 'access_token' not in self.cfg):
            print('Visit', auth.get_authorization_url(), 'and grant plutor_wifi '
                  'access.')
            verifier = input ('Then, copy the "oauth_verifier" here: ')
            access_token = auth.get_access_token(verifier)
            self.cfg['request_token'] = auth.request_token
            self.cfg['access_token'] = access_token

            print('Writing new cfg:')
            print(json.dumps(self.cfg, indent=4))
            self.write_cfg()
            sys.exit(1)

        auth.request_token = self.cfg['request_token']
        auth.set_access_token(*self.cfg['access_token'])
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
        tries = 5
        while(tries):
            tries -= 1
            print("Running fast.com (remaining tries: %d)" % tries)
            cp = subprocess.run(['fast-cli', '-s'], stdout=subprocess.PIPE)
            print(cp)
            if cp.returncode != 0:
                print('Bad return code %d' % cp.returncode)
                continue
            if 'NaN bps' in str(cp.stdout):
                print('Bad result:\n%s' % cp.stdout)
                continue
            result = cp.stdout.split()
            val = result[0]
            return (float(val), None, None)
        return None

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
        return (data['Download']['Value'], data['Upload']['Value'], data['MinRTT']['Value'], data['DownloadRetrans']['Value'])

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
        xs = [[], [], [], [], [], [], [], []]
        ys = [[], [], [], [], [], [], [], []]
        for run in self.hist:
            stamp = datetime.datetime.fromtimestamp(run['timestamp'])
            totalup = 0
            totaldown = 0
            ups = 0
            downs = 0
            if 'speedtest' in run['data']:
                totaldown += run['data']['speedtest'][0]
                downs += 1
                ys[0].append(run['data']['speedtest'][0])
                xs[0].append(stamp)
                totalup += run['data']['speedtest'][1]
                ups += 1
                ys[4].append(run['data']['speedtest'][1])
                xs[4].append(stamp)
            if 'mlab' in run['data']:
                totaldown += run['data']['mlab'][0]
                downs += 1
                ys[1].append(run['data']['mlab'][0])
                xs[1].append(stamp)
                totalup += run['data']['mlab'][1]
                ups += 1
                ys[5].append(run['data']['mlab'][1])
                xs[5].append(stamp)
            if 'fastcom' in run['data']:
                totaldown += run['data']['fastcom'][0]
                downs += 1
                ys[2].append(run['data']['fastcom'][0])
                xs[2].append(stamp)
            if 'chromedl' in run['data']:
                totaldown += run['data']['chromedl'][0]
                downs += 1
                ys[3].append(run['data']['chromedl'][0])
                xs[3].append(stamp)
            if downs:
                ys[6].append(totaldown/downs)
                xs[6].append(stamp)
            if ups:
                ys[7].append(totalup/ups)
                xs[7].append(stamp)

        # Calculate running averages for ys[6] and ys[7]
        for ynum in (6, 7):
            win = []
            for n, y in enumerate(ys[ynum]):
                x = xs[ynum][n]
                win.append((x, y))
                # remove all old values
                win = list(filter(lambda e: x-e[0] < datetime.timedelta(hours=3), win))
                # calculate the window avg
                ys[ynum][n] = sum(map(lambda e: e[1], win))/len(win)

        med_down = statistics.median(filter(None, ys[0]+ys[1]+ys[2]))
        med_up = statistics.median(filter(None, ys[3]+ys[4]))

        # Plot data including options
        fig, ax = plt.subplots(figsize=(8, 4.4), sharex=True)
        ax.xaxis.set_major_formatter(dates.DateFormatter('%H:%M'))
        ax.minorticks_on()
        for n, x in enumerate(xs):
            if n > 5:
                break
            ax.plot(x, ys[n],
                    linestyle='',
                    marker='v' if (n < 4) else '^',
                    markersize=3,
                    color=COLORS[n % len(COLORS)],
                    alpha=0.5)

        # Plot averages for down and up
        ax.plot(xs[6], ys[6],
                linestyle='-',
                linewidth=2,
                color='tab:pink')
        ax.plot(xs[7], ys[7],
                linestyle='-',
                linewidth=2,
                color='tab:purple')


        # Add plot details
        plt.ylabel('Mbps')
        plt.legend(['speedtest down', 'mlab down', 'fast.com down', 'chrome down',
                    'speedtest up', 'mlab up', 'avg down', 'avg up'],
                    fontsize='small',
                    ncol=2)

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
    p.auth()

    do_tweet = (args.force_tweet or p.tweet_due(8*60*60)) and not args.only_test
    if not args.skip_test:
        data = p.run_speedtests()
        if data:
            p.save_data(data, do_tweet)
        
    if args.dry_run:
        p.generate_graph()
        print("Graph generated")
    elif do_tweet:
        p.tweet_history(24*60*60)
    else:
        print("Skipping tweet")


if __name__ == "__main__":
    main()

