import unittest
try:
    from .test_research_store import fixture,create,accept
    from . import deliverables, research_store as store, research_service as service, workflow
except ImportError:
    from test_research_store import fixture,create,accept
    import deliverables, research_store as store, research_service as service, workflow
class DeliverableTests(unittest.TestCase):
    def setUp(self):self.c,self.card,self.user=fixture()
    def tearDown(self):self.c.close()
    def test_derived_summary_replaces_old_draft_and_defense_references(self):
        old=dict(id='PV1',revision=1)
        latest=dict(id='PV1',revision=2)
        self.card['research']['selected_deliverable']=latest
        self.card['research']['objects']=[
            dict(id='old-answer',kind='defense',status='confirmed',revision=2,content=dict(deliverable_ref=old,answer_ref='old')),
            dict(id='current-answer',kind='defense',status='confirmed',revision=3,content=dict(deliverable_ref=latest,answer_ref='new')),
        ]
        data=dict(summary='核对固定开题计划及对应答辩。',summary_origin='program_reference',summary_refs=[old],
                  defense_refs=[dict(id='old-answer', revision=2)])
        derived=workflow.derived_stage_data(self.card,5,data)
        self.assertEqual(derived['summary_refs'],[latest,dict(id='current-answer',revision=3)])
        self.assertEqual(derived['defense_refs'],[dict(type='object',id='current-answer',revision=3)])

    def test_immutable_version_and_dependency_review(self):
        contents={'problem':dict(puzzle='困惑',grouping_reason='共同点',candidate_explanations='解释'), 'rq':dict(population_or_object='对象',conditions='条件',question='问题',scope='范围',promised_conclusion='承诺'), 'method':dict(research_type='qualitative',materials='材料',procedure='程序',analysis='分析',variables_or_concepts='概念',feasibility='资源',limits='局限',ethics='无参与者，不适用')}
        for kind,content in contents.items():create(self.c,self.card,self.user,kind,kind,content);accept(self.c,self.card,self.user,kind)
        body=dict(chapters={k:'合成测试章节' for k in deliverables.CHAPTERS},object_refs=[dict(type='object',id=k,revision=2) for k in contents])
        self.card['materials']=[{'id':'S','title':'合成来源原记录','url':'https://example.test/paper'}]
        self.card['steps'][2]['data']['source_comparisons']=[{'reference':'S'}]
        service.capture_reading_sources(self.c,self.card)
        self.card['materials'][0]['title']='后来的来源说明'
        d=deliverables.create(self.c,self.card,body,self.user)
        self.assertEqual(d['evidence_snapshots'][0]['content']['title'],'合成来源原记录')
        original=store.dump(d)
        self.card['steps'][4]['status']='complete';self.card['current_step']=6
        self.card['steps'][4]['data'].update(summary='旧稿与答辩',summary_origin='program_reference',
                                           summary_refs=[{'id':d['id'],'revision':1}],revision_notes='旧稿核对')
        deliverables.create(self.c,self.card,body,self.user)
        self.assertEqual(self.card['current_step'],5)
        self.assertEqual(self.card['steps'][4]['status'],'active')
        self.assertEqual(self.card['steps'][4]['data'],{})
        accept(self.c,self.card,self.user,'method',{'set':{'limits':'新限制'}})
        self.assertEqual(store.dump(store.rows(self.c,'deliverable_versions','P')[0]),original)
        self.assertIn({'id':d['id'],'revision':d['revision']},self.card['research_state']['deliverable_reviews'])
        with self.assertRaises(ValueError):deliverables.create(self.c,self.card,body,self.user)
if __name__=='__main__':unittest.main()
