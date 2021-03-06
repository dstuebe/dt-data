#!/usr/bin/env python

"""
Worker VM ctx-agent script.

1. Parse the Chef config JSON before running chef-solo and determine where the
   /opt/dt-data directory should come from:
   
   a. Archive URL: download off the network
   b. git checkout
   c. Filesystem: don't touch /opt/dt-data
   
   Also uses the config JSON to determine whether or not to use DEBUG.
   
2. Run chef-solo

"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import simplejson as json

DT_DATA_DIR = '/opt/dt-data'

X = """"""

def parse_conf(chefjson_path):
    if not os.path.exists(chefjson_path):
        raise Exception("File does not exist: %s" % chefjson_path)
    
    f = open(chefjson_path)
    chefjson = json.load(f)
    f.close()
    return chefjson
    
def get_choices(chefjson):
    
    confchoices = { "chef_debug_level": "debug",
                    "use_filesystem": False,
                    "use_http": False,
                    "use_git": False,
                    "archive_url": None,
                    "git_repo": None,
                    "git_branch": None,
                    "git_commit": None }
    
    # For backwards compatibility this is currently not an error.
    # Process will error out later on if dt-data does not exist already.
    if not chefjson.has_key("dtdata"):
        confchoices["use_filesystem"] = True
        return confchoices
    
    dtdata = chefjson["dtdata"]
    
    if dtdata.has_key("chef_debug_level"):
        confchoices["chef_debug_level"] = dtdata["chef_debug_level"]
    
    if not dtdata.has_key("retrieve_method"):
        raise Exception("'retrieve_method' is required in dtdata configuration")
        
    if dtdata["retrieve_method"] == "filesystem":
        confchoices["use_filesystem"] = True
        return confchoices
    elif dtdata["retrieve_method"] == "archive":
        confchoices["use_http"] = True
        if not dtdata.has_key("archive_url"):
            raise Exception("'archive_url' is required for archive retrieve_method")
        confchoices["archive_url"] = dtdata["archive_url"]
        return confchoices
    elif dtdata["retrieve_method"] == "git":
        confchoices["use_git"] = True
        if not dtdata.has_key("git_repo"):
            raise Exception("'git_repo' is required for git retrieve_method")
        confchoices["git_repo"] = dtdata["git_repo"]
        if not dtdata.has_key("git_branch"):
            raise Exception("'git_branch' is required for git retrieve_method")
        confchoices["git_branch"] = dtdata["git_branch"]
        if not dtdata.has_key("git_commit"):
            raise Exception("'git_commit' is required for git retrieve_method")
        confchoices["git_commit"] = dtdata["git_commit"]
        return confchoices
    else:
        raise Exception("Unknown retrieve_method '%s'" % dtdata["retrieve_method"])

def download_dtdata(confchoices):
    """Assumes tar.gz file.
    """
    
    try:
        if os.path.exists(DT_DATA_DIR):
            shutil.move(DT_DATA_DIR, "/opt/old_dt_data")
    except:
        print >>sys.stderr, "Problem backing up old dt-data:\n"
        traceback.print_tb(sys.exc_info()[2])
    
    dtarchive = "dt-data.tar.gz"
    tmpdir = tempfile.mkdtemp()
    os.chdir(tmpdir)
    
    tries = 3
    while True:
        try:
            subprocess.check_call(['wget', '-O', dtarchive, confchoices["archive_url"]])
            break
        except:
            print >>sys.stderr, "Problem retrieving dt-data archive:\n"
            traceback.print_tb(sys.exc_info()[2])
            tries -= 1
            if tries == 0:
                raise Exception("Giving up on dt-data archive GET")
            time.sleep(2)
            
    subprocess.check_call(['tar', "xzf", dtarchive])
    os.remove(dtarchive)
    subprocess.check_call(['mv', "dt-data", DT_DATA_DIR])
    
def git_dtdata(confchoices):
    
    if not os.path.exists(DT_DATA_DIR):
        subprocess.check_call(['git', 'clone', confchoices["git_repo"], DT_DATA_DIR])
        
    os.chdir(DT_DATA_DIR)
    
    subprocess.check_call(['git', 'fetch'])
    
    subprocess.check_call(['git', 'checkout', '-b', "activebranch", "origin/%s" % confchoices["git_branch"]])
    
    subprocess.check_call(['git', 'pull']) # This makes HEAD meaningful
    
    subprocess.check_call(['git', 'reset', "--hard", confchoices["git_commit"]])
    
def run_chef_solo(confchoices, chefjson_path):
    os.chdir(DT_DATA_DIR)
    conf = os.path.join(DT_DATA_DIR, 'cookbooks/nimbus_context_agent/extra/chefconf.rb')
    debug_level = confchoices["chef_debug_level"]
    subprocess.check_call(['chef-solo', '-l', debug_level, '-c', conf, '-j', chefjson_path])

def main(args=sys.argv):
    try:
        chefjson_path = sys.argv[1]
        chefjson = parse_conf(chefjson_path)
        confchoices = get_choices(chefjson)
    except:
        print >>sys.stderr, "Problem with chef configuration file:\n"
        traceback.print_tb(sys.exc_info()[2])
        return 1
        
    try:
        if confchoices["use_filesystem"]:
            if not os.path.exists(DT_DATA_DIR):
                print >>sys.stderr, "Told to use filesystem method but directory does not exist: %s" % DT_DATA_DIR
                return 2
        elif confchoices["use_http"]:
            download_dtdata(confchoices)
        elif confchoices["use_git"]:
            git_dtdata(confchoices)
    except:
        print >>sys.stderr, "Problem establishing dt-data:\n"
        traceback.print_tb(sys.exc_info()[2])
        return 2
        
    try:
        run_chef_solo(confchoices, chefjson_path)
    except:
        print >>sys.stderr, "Problem running chef-solo:\n"
        traceback.print_tb(sys.exc_info()[2])
        return 3
    
if __name__ == '__main__':
    sys.exit(main())
