"""Synthetic review/preparation integration; no analyst approval of real pilot data."""

from copy import deepcopy
import json
from pathlib import Path
import uuid

import pytest

from asbuilt_matcher.cli import main
from asbuilt_matcher.pdf_extract import file_sha256
from asbuilt_matcher.pdf_study import run_study
from asbuilt_matcher.ocr import load_images
from asbuilt_matcher.views import create_views, apply_views, load_views, run_view_ocr, _scale_spec, read
from asbuilt_matcher.view_scale import revision


@pytest.fixture
def collection(tmp_path):
    pdf = pytest.importorskip('pymupdf')
    inputs = tmp_path / 'inputs'; inputs.mkdir()
    with pdf.open() as doc:
        p=doc.new_page(width=300,height=200)
        p.draw_line((10,50),(82,50))
        p.insert_text((10,80),'SYNTHETIC 1 INCH = 40 FEET')
        p.add_text_annot((150,40),'SYNTHETIC visible markup')
        p=doc.new_page(width=300,height=200)
        pix=pdf.Pixmap(pdf.csRGB,pdf.IRect(0,0,100,100),False);pix.clear_with(190)
        p.insert_image(p.rect,pixmap=pix);p.set_rotation(90)
        doc.save(inputs/'synthetic.pdf')
    cfg=tmp_path/'study.json';cfg.write_text(json.dumps({'input_directory':'inputs','max_preview_pixels':20000}))
    study=tmp_path/'study';run_study(cfg,study)
    spec={'bbox':[0,0,300,100],'view_type':'engineering_plan','reading_orientation':0,
          'engineering_relevance':'engineering','scale_mode':'unknown','distortion_notes':''}
    entries=[{'id':'plan','source_pdf':'synthetic.pdf','page_number':1,'spec':spec,'reason':'SYNTHETIC plan', 'ocr_focus_bbox':[5,55,290,95]},
             {'id':'profile','source_pdf':'synthetic.pdf','page_number':1,'spec':spec|{'bbox':[0,100,300,200],'view_type':'engineering_profile','scale_mode':'anisotropic'},'reason':'SYNTHETIC separate profile','ocr_focus_bbox':[5,110,290,190]},
             {'id':'scan','source_pdf':'synthetic.pdf','page_number':2,'spec':spec|{'reading_orientation':90},'reason':'SYNTHETIC scan','ocr_focus_bbox':[5,5,90,90]}]
    config=tmp_path/'views.json';config.write_text(json.dumps({'preparation':{'dpi':72,'max_pixels':20000},'views':entries}))
    out=tmp_path/'collection';create_views(study/'inspection.json',config,out)
    return out/'views.json'


def op(action,target='view',view_id='plan',**kwargs):
    return {'operation_id':str(uuid.uuid4()),'action':action,'target':target,'view_id':view_id,
            'author':'SYNTHETIC preparer','reviewer_type':'human','independent':False,'reason':'SYNTHETIC evidence review',**kwargs}


def commit(path,tmp_path,operations,name='next'):
    decision=tmp_path/(name+'-decisions.json');decision.write_text(json.dumps({'registry_sha256':file_sha256(path),'operations':operations}))
    out=tmp_path/name
    return apply_views(path,decision,out),out/'views.json'


def test_multiple_views_preserve_page_identity_annotations_and_rotation(collection):
    r=load_views(collection)
    assert len(r['views'])==3 and len(r['pages'])==2
    assert r['views'][0]['page_id']==r['views'][1]['page_id']
    scan=r['views'][2];im=r['images'][scan['image_id']]
    assert r['pages'][scan['page_id']]['original_rotation']==90
    assert im['includes_annotations'] and im['input_to_oriented']!=[1,0,0,1,0,0]
    assert all(v['verification_status']=='unverified' for v in r['views'])
    assert read(collection.parent/'handoff.json')['views']==[]
    assert len(read(collection.parent/'decisions-template.json')['operations'])==0
    assert r['map_crs'] is None


def test_approved_view_and_native_bar_produce_unregistered_handoff(collection,tmp_path):
    original=read(collection);v=original['views'][0];spec=v['spec']|{'scale_mode':'isotropic','distortion_notes':'SYNTHETIC uniform scale assessment'}
    s=_scale_spec(v,kind='bar',endpoints=[[10,50],[82,50]],ground_distance=40,ground_unit='foot',
        text='SYNTHETIC bar',source_reference=original['pages'][v['page_id']]['vectors_path'],source_method='native_vector',
        native_segment={'path_index':0,'item_index':0},view_revision=revision(spec),use='current_view',
        applicability_confirmed=True,distortion_checked=True)
    operations=[op('edit',spec=spec),op('review',status='verified',author='SYNTHETIC independent analyst',independent=True),
                op('add',target='scale',scale_id='measured',spec=s),
                op('review',target='scale',scale_id='measured',status='verified',author='SYNTHETIC independent analyst',independent=True)]
    before=file_sha256(collection)
    r,path=commit(collection,tmp_path,operations)
    handoff=read(path.parent/'handoff.json')
    assert len(handoff['views'])==1
    h=handoff['views'][0]
    assert h['scale']['status']=='calibrated_effective_view_scale'
    assert h['map_crs'] is None and not h['registered'] and h['intended_future_crs']=='EPSG:2264'
    assert h['raster']['includes_annotations'] and h['tiff_preparation']['assign_map_crs'] is False
    assert h['scale_evidence'][-1]['spec']['ground_unit']=='foot'
    assert handoff['page_coordinates']['rotation']=='unrotated'
    assert r['views'][1]['scale_assessment']['axes']=={}
    assert file_sha256(collection)==before
    assert load_views(path)['snapshot_id']==r['snapshot_id']


def test_view_correction_preserves_unrelated_scale_approval_history(collection,tmp_path):
    r=read(collection);v=r['views'][0];spec=deepcopy(v['spec']);spec['distortion_notes']='SYNTHETIC inspected';spec['scale_mode']='isotropic'
    scale=_scale_spec(v,kind='bar',text='SYNTHETIC independently reviewed bar',source_reference='SYNTHETIC source',
        endpoints=[[10,50],[82,50]],ground_distance=40,ground_unit='foot',view_revision=revision(spec),
        use='current_view',applicability_confirmed=True,distortion_checked=True)
    r,path=commit(collection,tmp_path,[op('edit',spec=spec),op('review',status='verified',author='SYNTHETIC reviewer',independent=True),
        op('add',target='scale',scale_id='bar',spec=scale),op('review',target='scale',scale_id='bar',status='verified',author='SYNTHETIC reviewer',independent=True)],'accepted')
    previous=deepcopy(r['views'][0]['scales'][-1])
    spec['bbox']=[1,1,299,99]
    r,path=commit(path,tmp_path,[op('edit',spec=spec,author='SYNTHETIC corrector')],'corrected')
    assert r['views'][0]['verification_status']=='unverified'
    assert r['views'][0]['scales'][-1]==previous
    assert r['views'][0]['history'][-1]['before']['verification_status']=='verified'
    assert r['views'][0]['scale_assessment']['axes']=={}
    assert 'Reconfirm' in ' '.join(r['views'][0]['scale_assessment']['missing_evidence'])
    assert read(path.parent/'handoff.json')['views']==[]


@pytest.mark.parametrize('change',['ai','self','no_independence','unknown_scale','bad_native','incomplete_bar','bad_hash','duplicate_op','foreign_image','bad_effort'])
def test_invalid_review_decisions_are_atomic(collection,tmp_path,change):
    v=read(collection)['views'][0]
    operation=op('review',status='verified',author='SYNTHETIC reviewer',independent=True)
    if change=='ai':operation['reviewer_type']='ai'
    if change=='self':operation['author']=v['last_evidence_author']
    if change=='no_independence':operation['independent']=False
    if change=='unknown_scale':operation.update(target='scale',scale_id='absent')
    if change in {'bad_native','incomplete_bar','foreign_image'}:
        s=_scale_spec(v,kind='bar',text='SYNTHETIC new bar',source_reference='SYNTHETIC reference')
        if change=='bad_native':s.update(source_method='native_vector',native_segment={'path_index':0,'item_index':0},endpoints=[[20,20],[80,20]])
        if change=='foreign_image':
            other=read(collection)['views'][2];s.update(coordinate_space='image',image_id=other['image_id'],endpoints=[[1,1],[50,50]])
        operation=op('add',target='scale',scale_id='new',spec=s)
    if change=='bad_effort':operation['elapsed_seconds']=-1
    operations=[operation]
    if change=='duplicate_op':operations.append(deepcopy(operation))
    if change=='incomplete_bar':operations.append(op('review',target='scale',scale_id='new',status='verified',author='SYNTHETIC reviewer',independent=True))
    decision=tmp_path/'invalid.json';decision.write_text(json.dumps({'registry_sha256':'0'*64 if change=='bad_hash' else file_sha256(collection),'operations':operations}))
    before=file_sha256(collection)
    with pytest.raises((ValueError,KeyError)):apply_views(collection,decision,tmp_path/'out')
    assert file_sha256(collection)==before and not (tmp_path/'out').exists()


def test_rejected_and_incomplete_approvals_do_not_reset_other_views(collection,tmp_path):
    r,path=commit(collection,tmp_path,[op('review',status='rejected',author='SYNTHETIC rejector',interactions=4,elapsed_seconds=12.5)])
    assert r['views'][0]['verification_status']=='rejected'
    assert r['views'][1]['verification_status']=='unverified'
    effort=read(path.parent/'review-effort.json')
    assert effort['self_reported_elapsed_seconds']==12.5 and effort['interactions']==4
    assert read(path.parent/'handoff.json')['views']==[]


@pytest.mark.parametrize('kind',['source','derived','js'])
def test_hash_validation_preserves_evidence(collection,kind):
    r=read(collection)
    path=Path(next(iter(r['external_files']))) if kind=='source' else collection.parent/('view_review.js' if kind=='js' else r['images'][r['views'][0]['image_id']]['file'])
    path.write_bytes(path.read_bytes()+b'SYNTHETIC tamper')
    with pytest.raises(ValueError,match='hash mismatch'):load_views(collection)


def test_review_replay_is_rejected(collection,tmp_path):
    decision=op('review',status='unreadable')
    _,path=commit(collection,tmp_path,[decision],'first')
    with pytest.raises(ValueError,match='unreplayed'):commit(path,tmp_path,[decision],'replayed')


def test_selective_ocr_reuses_adapter_without_reference_scoring(collection,tmp_path):
    # Engine deliberately missing in tests; preparation/comparison still works and is audited.
    config={'variants':[{'id':'baseline'}],'max_pixels':100000,'timeout_seconds':1}
    r=run_view_ocr(collection,tmp_path/'ocr',config=config,executable=str(tmp_path/'absent-tesseract.exe'))
    assert r['ocr_comparison']['attempts']==3
    assert all(v['verification_status']=='unverified' for v in r['views'])
    data=read(tmp_path/'ocr'/r['ocr_comparison']['file'])
    assert data['accuracy'] is None
    assert all(x['status']=='blocked_engine' for x in data['comparisons'])
    targets=load_images(tmp_path/'ocr'/'ocr-targets.json')
    assert len(targets)==3 and all('text' not in x for x in targets)
    assert load_views(tmp_path/'ocr'/'views.json')['snapshot_id']==r['snapshot_id']
    # Repeating recognition keeps the old run and targets intact rather than colliding.
    again=run_view_ocr(tmp_path/'ocr'/'views.json',tmp_path/'ocr-repeat',config=config,executable=str(tmp_path/'absent-tesseract.exe'))
    assert again['ocr_comparison']['attempts']==3
    assert again['ocr_comparison']['file']!=r['ocr_comparison']['file']
    assert load_views(tmp_path/'ocr-repeat'/'views.json')['snapshot_id']==again['snapshot_id']


def test_cli_review_and_snapshot_overwrite_guard(collection,tmp_path,capsys):
    decision=tmp_path/'decisions.json';decision.write_text(json.dumps({'registry_sha256':file_sha256(collection),'operations':[]}))
    assert main(['views-apply',str(collection),str(decision),'--output',str(tmp_path/'cli')])==0
    assert json.loads(capsys.readouterr().out)['views']==3
    assert main(['views-apply',str(collection),str(decision),'--output',str(tmp_path/'cli')])==1
