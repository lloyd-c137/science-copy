"""SQLite persistence; callers own the transaction. No helper commits."""
import json, uuid, hashlib
from datetime import datetime
class Conflict(ValueError): pass
def now(): return datetime.now().astimezone().isoformat(timespec='microseconds')
def uid(p): return p+uuid.uuid4().hex[:20]
def dump(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def init_schema(c):
    for sql in (
        'CREATE TABLE IF NOT EXISTS research_objects(project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id))',
        'CREATE TABLE IF NOT EXISTS object_revisions(project_id TEXT, object_id TEXT, revision INTEGER, data TEXT NOT NULL, PRIMARY KEY(project_id,object_id,revision))',
        'CREATE TABLE IF NOT EXISTS research_links(project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id))',
        'CREATE TABLE IF NOT EXISTS research_events(project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id))',
        'CREATE TABLE IF NOT EXISTS research_reference_snapshots(project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id))',
        'CREATE TABLE IF NOT EXISTS deliverable_versions(project_id TEXT, id TEXT, revision INTEGER, data TEXT NOT NULL, PRIMARY KEY(project_id,id,revision))'):
        c.execute(sql)
def rows(c, table, pid):
    if table not in {'research_objects','object_revisions','research_links','research_events','research_reference_snapshots','deliverable_versions'}: raise ValueError('Invalid table')
    return [json.loads(r[0]) for r in c.execute('SELECT data FROM '+table+' WHERE project_id=? ORDER BY rowid',(pid,))]
def get(c,pid,oid,revision=None):
    if revision is None: row=c.execute('SELECT data FROM research_objects WHERE project_id=? AND id=?',(pid,oid)).fetchone()
    else: row=c.execute('SELECT data FROM object_revisions WHERE project_id=? AND object_id=? AND revision=?',(pid,oid,revision)).fetchone()
    if not row: raise ValueError('本项目不存在对象或修订：'+str(oid))
    return json.loads(row[0])
def save_object(c,row,expected):
    old=c.execute('SELECT data FROM research_objects WHERE project_id=? AND id=?',(row['project_id'],row['id'])).fetchone()
    if (json.loads(old[0])['revision'] if old else 0)!=expected: raise Conflict('对象版本已变化。')
    c.execute('INSERT INTO object_revisions VALUES(?,?,?,?)',(row['project_id'],row['id'],row['revision'],dump(row)))
    c.execute('INSERT INTO research_objects VALUES(?,?,?) ON CONFLICT(project_id,id) DO UPDATE SET data=excluded.data',(row['project_id'],row['id'],dump(row)))
def pointer(c,row): c.execute('UPDATE research_objects SET data=? WHERE project_id=? AND id=?',(dump(row),row['project_id'],row['id']))
def save_link(c,row): c.execute('INSERT INTO research_links VALUES(?,?,?) ON CONFLICT(project_id,id) DO UPDATE SET data=excluded.data',(row['project_id'],row['id'],dump(row)))
def event(c,pid,kind,user,**kw):
    row=dict(id=uid('EV'),project_id=pid,kind=kind,created_by=user,created_at=now(),**kw)
    c.execute('INSERT INTO research_events VALUES(?,?,?)',(pid,row['id'],dump(row))); return row

def snapshot(c,card,ref):
    typ=ref.get('type'); rid=ref.get('id'); pid=card['id']
    if 'content' in ref or 'sha256' in ref: raise ValueError('依据快照只能由服务从原记录捕获。')
    if ref.get('snapshot_id'):
        row=next((r for r in rows(c,'research_reference_snapshots',pid) if r['id']==ref['snapshot_id'] and r['ref_type']==typ and r['ref_id']==rid),None)
        if not row: raise ValueError('引用快照不存在。')
        return {'type':typ,'id':rid,'snapshot_id':row['id']}
    pool={'file':card.get('files',[]),'source':card.get('materials',[]),'claim':[r for r in card.get('quality',{}).get('records',[]) if r.get('kind')=='claim']}
    original=next((r for r in pool.get(typ,[]) if r.get('id')==rid or (typ=='source' and r.get('url')==rid)),None)
    if not original or original.get('lead'): raise ValueError('依据须是本项目已登记的材料或主张。')
    digest=hashlib.sha256(dump(original).encode()).hexdigest()
    sid='RS'+hashlib.sha256((typ+str(rid)+digest).encode()).hexdigest()[:24]
    row=dict(id=sid,project_id=pid,ref_type=typ,ref_id=rid,content=original,sha256=digest,captured_at=now())
    c.execute('INSERT OR IGNORE INTO research_reference_snapshots VALUES(?,?,?)',(pid,sid,dump(row)))
    return {'type':typ,'id':rid,'snapshot_id':sid}
