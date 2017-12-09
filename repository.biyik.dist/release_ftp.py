# -*- coding: utf-8 -*-
import sys
import os
import shutil,stat
import urllib2
import urllib
import md5
import datetime
import time
import re
from distutils.version import StrictVersion, LooseVersion
from xml.dom import minidom
import ftplib
import codecs

import shlex
from subprocess import Popen, PIPE

def fixzip(zipFile):  
	f = open(zipFile, 'r+b')  
	data = f.read()  
	pos = data.find('\x50\x4b\x05\x06') # End of central directory signature  
	if (pos > 0):  
		 print "Trancating file at location " + str(pos + 22)  
		 f.seek(pos + 22)   # size of 'ZIP end of central directory record' 
		 f.truncate()  
		 f.close()  

def runcmd(cmd,cwd):
	args = shlex.split(cmd)
	proc = Popen(args, stdout=PIPE, stderr=PIPE,cwd=cwd)
	out, err = proc.communicate()
	exitcode = proc.returncode
	#print out[:-1]
	return exitcode, out, err

dirname=os.path.dirname(os.path.realpath(__file__))
username="hbiyik"
password=sys.argv[1]
#distrepo={"repo":"repository.boogie.dist",
#		  "branch":"master"}

#distrepo={"repo":"distro","server":"boogie.us.to","uname":"boogie.us.to"}
ftp_prefix="/"

packs=(
	   ("script.module.htmlement", "master"),
	   ("script.module.sublib", "release"),
	   ("service.subtitles.planetdp", "release"),
	   ("service.subtitles.turkcealtyazi", "release"),
	   ("service.subtitles.subscene", "release"),
	   ("repository.biyik", "release"),
	   )

datesince=int(time.mktime(datetime.datetime(2000,1,1).timetuple()))

versions={}
global ftp

#domain name or server ip:

def remove_readonly(func, path, excinfo):
	os.chmod(path, stat.S_IWRITE)
	func(path)

def download_zip(pack,branch):
	urllib2.urlopen("https://github.com/%s/%s/archive/%s.zip"%(uname,pack,branch))

def ftp_connect():
	global ftp
	ftp = ftplib.FTP(distrepo["server"])
	ftp.login(user=distrepo["uname"], passwd = sys.argv[2])

def ftp_disconnect():
	global ftp
	ftp.quit()

def ftp_chdir(fullpath):
	try:
		ftp.cwd(fullpath)
	except ftplib.error_perm,msg:
		if msg.message.startswith("550"):
			ftp.mkd(fullpath)
			ftp.cwd(fullpath)

def ftp_emdir(fullpath):
	ftp_chdir(fullpath)
	allfiles = ftp.nlst()
	for file in allfiles:
		if not file in [".",".."]:
			ftp.delete(file)
			print "FTP: Deleted Remote: %s "% file

def ftp_updir(dst):
	for f in os.listdir(dst):
		if os.path.isfile(os.path.join(dst, f)):
			ftp.storbinary('STOR '+f, open(os.path.join(dst,f), 'rb'))
			print "FTP: Uploaded: %s "% os.path.join(dst,f)

def gitcli():
	for pack,branch in packs:
		stage_path=os.path.join(dirname,"staging")
		repo_path= os.path.join(stage_path,pack)
		if os.path.exists(repo_path):
			shutil.rmtree(repo_path,onerror=remove_readonly)
		os.makedirs(repo_path)
		repo_url = 'https://github.com/%s/%s.git'%(username,pack)
		c,o,e=runcmd("git init",repo_path)
		c,o,e=runcmd("git remote add origin %s "%repo_url,repo_path)
		c,o,e=runcmd("git fetch --tags",repo_path)
#		c,o,e=runcmd("git tag -l",repo_path)
#		c,o,e=runcmd("git show-ref --head",repo_path)
		c,o,e=runcmd("git ls-remote",repo_path)
		last_version="0.0.0"
		last_hash=None
		head_hash=None
		for release in o.split("\n"):
			try:
				(hash,vers)=release.split(unichr(9))
			except:
				continue
			if "^{}" in vers:
				continue
			if "tags/" in vers:
				version=vers.split("/")[-1]
			elif "/"+branch in vers:
				head_hash=hash
				continue
			else:
				continue

			if LooseVersion(version)>LooseVersion(last_version):
				last_version=version
				last_hash=hash

		
		versions[pack]=last_version

		if not last_version=="0.0.0":
			c,o,e=runcmd("git log origin/"+branch+" "+head_hash+" -n 1 --format=%at",repo_path)
			head_ts=int(o)
			c,o,e=runcmd("git log "+last_hash+" -n 1 --format=%at",repo_path)
			last_ts=int(o)

		c,o,e=runcmd("git fetch --all",repo_path)
		c,o,e=runcmd("git pull https://%s:%s@github.com/%s/%s.git %s"%(username,password,username,pack,branch),repo_path)
		addonxml = minidom.parse(os.path.join(repo_path,"addon.xml"))
		addon = addonxml.getElementsByTagName("addon")

		requires=addon[0].getElementsByTagName("requires")
		if len(requires)>0:
			imports=requires[0].getElementsByTagName("import")
			for imprt in imports:
				reqname=imprt.attributes["addon"].value
				reqver=imprt.attributes["version"].value
				if reqname in versions.keys() and LooseVersion(versions[reqname])>LooseVersion(reqver):
					imprt.attributes["version"].value=versions[reqname]
					print "%s requirement for %s bumped to: %s"%(reqname,pack,versions[reqname])
				else:
					print "%s requirement for %s skipped, no new release found"%(reqname,pack)

		if not last_version=="0.0.0" and head_ts>last_ts or last_version=="0.0.0":
#			x=open(os.path.join(repo_path,"addon.xml")).read()
			new_version=LooseVersion(last_version).version
			new_version[2]=	str(int(new_version[2])+1)
			new_version=[str(x) for x in new_version]
			new_version = ".".join(new_version)
			versions[pack]=new_version
			vers = new_version
			print "%s: Found new version %s since %s"%(pack,new_version,last_version)
			print "Do you want to continue with the release? (y/n)"
			ans=raw_input()
			if not ans.lower()=="y":
				print "Skipping addon."
				continue
			###update git changelog on changelog.txt
			c,log,e=runcmd('git log --pretty=format:"%ad: %s" --date short',repo_path)
			changelog=open(os.path.join(repo_path,"changelog.txt"),"w")
			changelog.truncate()
			changelog.write(log)
			changelog.close()
			print "Changelog updated in addon"
			###create version release revision on git and tag it
			c,o,e=runcmd("git add -A .",repo_path)
			c,o,e=runcmd("git commit -m '%s Version Release'"%new_version,repo_path)
			c,o,e=runcmd("git tag -a %s -m '%s Version Release'"%(new_version,new_version),repo_path)
			c,o,e=runcmd("git push https://%s:%s@github.com/%s/%s.git HEAD:%s "%(username,password,username,pack,branch),repo_path)
			c,o,e=runcmd("git push https://%s:%s@github.com/%s/%s.git HEAD:%s --tags  "%(username,password,username,pack,branch),repo_path)
			print "%s: Created new tag on github"%pack
			#transfer new zipball
			#ftp_connect()
			#ftp_chdir(ftp_prefix+distrepo["repo"])
			#ftp_chdir(ftp_prefix+distrepo["repo"]+"/"+pack)
			#ftp_emdir(ftp_prefix+distrepo["repo"]+"/"+pack)
			#ftp_updir(pack_path)
			#ftp_disconnect()
			print "%s: Distribution repo updated"%pack
		else:
			print "%s: No new commits version:%s. Skipping"%(pack,last_version)
			vers = last_version
		###update to new version on addon.xml
		addon[0].attributes["version"].value=vers
		with codecs.open(os.path.join(repo_path, "addon.xml"), "w", "utf-8") as out:
			addonxml.writexml(out, encoding="utf-8")
		print "%s: version bumped in addon.xml"%pack

		###pack new zipball and update binaries
		pack_path=os.path.join(dirname,pack)
		if os.path.exists(pack_path):
			shutil.rmtree(pack_path,onerror=remove_readonly)
		os.makedirs(pack_path)
		shutil.rmtree(os.path.join(repo_path,".git"),onerror=remove_readonly)
		shutil.make_archive(os.path.join(pack_path,"%s-%s"%(pack,vers)), 'zip', stage_path,pack)
		fixzip(os.path.join(pack_path,"%s-%s"%(pack,vers)) + ".zip")
		metas=["icon.png","fanart.jpg","changelog.txt"]
		for meta in metas:
			if os.path.exists(os.path.join(repo_path,meta)):
				if meta=="changelog.txt":
					shutil.copy2(os.path.join(repo_path,meta),os.path.join(pack_path,"changelog-%s.txt"%vers))
				else:
					shutil.copy2(os.path.join(repo_path,meta),os.path.join(pack_path,meta))
		print "%s: New zipball created on distribution directory"%pack
		##update addons.xml
		addonsxml=minidom.parse(os.path.join(dirname,"addons.xml"))
		addons=addonsxml.getElementsByTagName("addons")[0]
		for addontag in addons.getElementsByTagName("addon"):
			if addontag.attributes["id"].value==pack:
				addons.removeChild(addontag)
		addons.appendChild(addon[0])
		with codecs.open("addons.xml", "w", "utf-8") as out:
			addonsxml.writexml(out,encoding="UTF-8")
		
		##update addons.xml.md5
		m = md5.new(open(os.path.join(dirname,"addons.xml")).read()).hexdigest()
		open(os.path.join(dirname,"addons.xml.md5"),"wb").write(m)
		print "%s: addons.xml and md5 is updated"%pack
		print "~~~~~~~~~~~~~~~~~~~~~ %s END OF ADDON UPDATE ~~~~~~~~~~~~~~~~~~~~~\n" %pack
	#ftp_connect()
	#ftp_chdir(ftp_prefix+distrepo["repo"])
	#ftp_updir(dirname)
	#ftp_disconnect()
gitcli()