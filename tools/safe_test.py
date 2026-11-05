"""Run pytest while redacting local credentials, including decoded DSN passwords, from all output."""
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote,urlsplit


def secrets_on_disk(root):
    values=[]
    for path in (root/'.env',root/'.env.local'):
        if not path.exists():continue
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            key,value=line.split('=',1);value=value.strip().strip('\"\'')
            if any(word in key for word in ('KEY','SECRET','TOKEN','DB_URL','TEST_NUMBERS')) and len(value)>=8:
                values.append(value)
                if 'DB_URL' in key:
                    password=urlsplit(value).password
                    if password:values.extend((password,unquote(password)))
    return sorted(set(values),key=len,reverse=True)


def main():
    private=secrets_on_disk(Path(__file__).resolve().parents[1])
    process=subprocess.Popen([sys.executable,'-m','pytest',*sys.argv[1:]],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,encoding='utf-8',errors='replace')
    for line in process.stdout:
        for value in private:line=line.replace(value,'<redacted>')
        print(line,end='',flush=True)
    return process.wait()


if __name__=='__main__':
    sys.exit(main())
