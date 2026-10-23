import hashlib,json,os,pathlib,resource,sys
root=pathlib.Path(sys.argv[1]);cfg=json.loads((root/'client-command.json').read_text());soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
assert os.getuid()==501 and os.geteuid()==501
assert hard==resource.RLIM_INFINITY or hard>=32768
resource.setrlimit(resource.RLIMIT_NOFILE,(32768,32768));env=os.environ.copy();env.update({'GOMAXPROCS':'2','GODEBUG':'gctrace=1'})
binary=cfg['argv'][0];assert hashlib.sha256(pathlib.Path(binary).read_bytes()).hexdigest()==cfg['expected_sha256']
witness={'pid':os.getpid(),'pgid':os.getpgrp(),'uid':os.getuid(),'euid':os.geteuid(),'nofile':resource.getrlimit(resource.RLIMIT_NOFILE),'env':{k:env[k] for k in ['GOMAXPROCS','GODEBUG']},'binary_sha256':cfg['expected_sha256'],'limit_witness':'actual same PID immediately before exec; exec preserves RLIMIT_NOFILE; fixed child hard limit also prevents runtime raising above32768'}
(root/'client-actual.json').write_text(json.dumps(witness,indent=2)+'\n');os.execve(binary,cfg['argv'],env)
