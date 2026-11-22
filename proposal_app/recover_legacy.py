"""Recover this reviewed legacy conversation into stage drafts without inventing completion."""
import argparse
import json
from pathlib import Path
import sqlite3
import uuid

if __package__:
    from . import server
    from .project_archive import ProjectArchive
else:
    import server
    from project_archive import ProjectArchive


def recover(db, pid, apply=False):
    archive=ProjectArchive(Path(db).resolve().with_suffix(".coaching"))
    with server.connect(db) as conn:
        row=conn.execute("SELECT card,student FROM projects WHERE id=?",(pid,)).fetchone()
        if not row: raise ValueError("项目不存在")
        card=json.loads(row["card"])
        if card.get("legacy_recovered"): return {"status":"already recovered","version":card["version"]}
        choice=card["steps"][2]["data"].get("choice","")
        marker="学生已核对并确认供老师审阅的开题稿，正文如下："
        if marker not in choice: raise ValueError("该项目不符合已审查的恢复条件")
        draft=choice.split(marker,1)[1].strip()
        fields={}
        for line in draft.splitlines():
            if "：" in line:
                key,value=line.split("：",1);fields[key]=value
        required=["研究问题","选题依据与预期价值","研究方法与年度范围","已完成小试","时间与分工","开题后的首项任务"]
        if any(key not in fields for key in required): raise ValueError("开题稿格式不完整，请人工核对")
        result={"project":pid,"source_version":card["version"],"restore_drafts":[4,5,6],"preserve_current_step":card["current_step"]}
        if not apply:return result
        # A SQLite backup includes history and attachments and is made before any mutation.
        backup=Path(db).with_name(Path(db).name+f".before-stages-{card['version']}.bak")
        with sqlite3.connect(backup) as dest: conn.backup(dest)
        before=server.dump(card)
        conn.execute("BEGIN IMMEDIATE")
        latest=json.loads(conn.execute("SELECT card FROM projects WHERE id=?",(pid,)).fetchone()["card"])
        if latest["version"] != card["version"]:
            raise ValueError("项目刚有新保存，请重新执行恢复以保留最新内容")
        fid=server.uid("F")
        content=("# 此前讨论与小试整理\n\n来源：原项目版本"+str(card["version"])+"，保留学生已确认的讨论正文。\n这是既有AI辅助计算记录，不是新增实验或独立验证。旧时间预算由当前26周安排替代。\n\n"+draft).encode("utf-8")
        conn.execute("INSERT INTO files VALUES(?,?,?,?)",(fid,pid,"此前小试与开题稿.md",content))
        card["files"].append({"id":fid,"name":"此前小试与开题稿.md","size":len(content),"url":"/api/files/"+fid,"created":server.now()})
        card["steps"][2]["data"]["choice"]="学生认可当前价值判断，选择先明确年度范围，并已确认两阶段模型方案。完整年度计划、小试与开题稿已整理到对应阶段草稿；当前贡献仍需文献对照与老师判断。"
        drafts={
            4:{"scope":fields["研究方法与年度范围"],"budget":"采用最新活动预算：26周，每周270分钟含教师30分钟，学生117小时、教师13小时、其余研究104小时。原30周135小时预算不再生效。",
               "resources":"已有文献与虚拟算例；目前不方便测量，独立对照资料是否可得仍待核实。",
               "roles":"AI协助检索、计算与绘图；学生核查来源、算例和解释；老师审查受力图与方案。",
               "unknown":"独立对照资料能否取得，以及拟新增贡献是否已被已有研究覆盖。","criterion":"用最简算例核查计算流程；将独立对照与针对性查重列为明确的后续任务。"},
            5:{"file_ids":[fid],"trial":fields["已完成小试"],"roles":"AI执行计算；学生参与模型假设、文献局限和循环验证判断。未记录实际耗时，不补造数据。",
               "finding":"虚拟算例与统一坐标计算说明计算实现初步可行，识别了参数拼接与姿势假设问题。",
               "limit":"没有完成真实坐姿的独立验证，尚不能证明新贡献；虚拟几何不能当作实测人体。",
               "change":"保留简化模型，头颈姿态暂不扩展。下一步补针对性文献对照与独立验证，交老师判断可开题范围。"},
            6:{"goal":fields["研究问题"],"value":fields["选题依据与预期价值"],"limits":"计算流程已跑通，但真实坐姿适用性、独立验证及新增贡献仍待核实；不能直接解释个人病因。",
               "first_task":fields["开题后的首项任务"]}}
        for n,data in drafts.items():
            card["steps"][n-1]["data"].update(data)
            card["steps"][n-1].update(recovered=True,draft_saved=True)
        card["recovery_notice"]="已从此前讨论整理年度范围、小试和开题稿。请核对已有阶段结论，无需重新聊一遍；尚未代替老师通过开题。"
        card["legacy_recovered"]={"source_version":card["version"],"created":server.now()}
        card["next_action"]="先核对已讨论过的研究价值判断，确认后结束本阶段；后续年度范围、小试与开题稿已有草稿可沿用。"
        conn.execute("INSERT INTO revisions VALUES(?,?,?)",(pid,card["version"],before))
        card["version"]+=1
        card["history"].append({"version":card["version"],"title":card["title"],"reason":"从既有对话恢复阶段草稿，保留原始历史与未完成状态","created":server.now(),"author":"系统整理","result_id":server.uid("R")})
        conn.execute("UPDATE projects SET card=? WHERE id=?",(server.dump(card),pid));conn.commit()
    discussions=archive.read(card,force=True)
    observations=[("循环验证","独立判断","主动指出用论文结果反推参数、再复算原结果属于循环验证。","下一次先提出独立对照来源，再看AI给的方案。"),
                  ("身体撑起来","提出问题","指出施加支撑时身体姿势也可能变化，提出影响模型假设的新因素。","先预测这一变化会怎样改变结果，再选择一个最小比较。")]
    for needle,dimension,observation,next_action in observations:
        evidence=next((m for c in discussions["conversations"] for m in c["messages"] if m["role"]=="user" and needle in m["text"]),None)
        if evidence:
            archive.reflect(card,{"dimension":dimension,"observation":observation,"next_action":next_action,"evidence_id":evidence["id"],"request_id":"recovered-"+dimension,"step":3})
    archive.export(card)
    return dict(result,status="recovered",version=card["version"],backup=str(backup))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--db",required=True);parser.add_argument("--project",required=True);parser.add_argument("--apply",action="store_true")
    args=parser.parse_args();print(json.dumps(recover(args.db,args.project,args.apply),ensure_ascii=False))
