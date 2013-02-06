import os
import sys
import subprocess

req_eggs = [
  'mock-1.0.1-py2.7.egg',
  'lockfile-0.9.1-py2.7.egg',
  'argparse-1.2.1-py2.7.egg',
  'unittest2-0.5.1-py2.7.egg',
  'pyserial-2.7_mb2.1-py2.7.egg'
]

opt_eggs = [
  'makerbot_driver-0.1.1-py2.7.egg'
]

def find_egg(paths, egg):
  for path in paths:
    egg_in_path = os.path.join(path, egg)
    if os.path.exists(egg_in_path):
      return egg_in_path
  return None

python_exe = sys.executable
env_dir = 'virtualenv'

search_paths = sys.argv[1:]
  
virtualenv_command = [
  python_exe,
  'virtualenv.py',
  '--never-download'
]

for path in search_paths:
  virtualenv_command.append('--extra-search-dir=' + path)

virtualenv_command.append(env_dir)

try:
  subprocess.check_call(virtualenv_command)
except subprocess.CalledProcessError as e:
  print 'something went wrong calling virtualenv:'
  print e
  sys.exit(2)


if 'win32' == sys.platform:
  virtualenv_easy_install = os.path.join(env_dir, 'Scripts', 'easy_install.exe')
else:
  print "I didn't expect this to be used on anything but windows, sorry."
  sys.exit(3)
e_install = [virtualenv_easy_install, '-q']

try:
  for egg in req_eggs:
    subprocess.check_call(e_install + [find_egg(search_paths, egg)])
except subprocess.CalledProcessError as e:
  print 'something went wrong installing the required eggs'
  sys.exit(4)
  
try:
  for egg in opt_eggs:
    egg_found = find_egg(search_paths, egg)
    if egg_found != None:
      subprocess.check_call(e_install + [egg_found])
    else:
      print 'skipping egg ' + egg
except subprocess.CalledProcessError as e:
  print 'something went wrong installing the optional eggs'
  sys.exit(5)