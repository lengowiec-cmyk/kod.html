"""Synthetic control-channel tests. No real Google Drive or EXE execution."""
from pathlib import Path
from urllib.request import Request
from unittest.mock import MagicMock
import json,shutil,uuid,zipfile
import pytest
from cryptography.exceptions import InvalidSignature
from pdfmanager.remote.admin_backend import AdminWorkspace
from pdfmanager.remote.deployment import automatic_unlock,attach_shared_folder,ingest_hellos,prepare_package,factory_envelope,verify_factory
from pdfmanager.remote.shared import FolderTransport,locate,MARKER,scoped_target
from pdfmanager.remote.storage import RemoteState,load_config
from pdfmanager.remote.client import ControlClient
from pdfmanager.remote.protocol import canonical,sign,verify_activation
from pdfmanager.remote.updater import apply

@pytest.fixture
def channel(tmp_path,monkeypatch):
    from pdfmanager.licensing import secure_storage
    monkeypatch.setattr(secure_storage,'_registry',None)
    parent=tmp_path/'Company Drive';parent.mkdir();(parent/'important.pdf').write_bytes(b'private original')
    owner=AdminWorkspace(tmp_path/'private');automatic_unlock(owner);config=attach_shared_folder(owner,parent)
    state=RemoteState(tmp_path/'employee');client=ControlClient(config,state)
    return owner,config,state,client,parent

def test_full_enrollment_block_code_and_release_documents_unchanged(channel,tmp_path):
    owner,config,state,client,parent=channel
    original={p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file() and not p.is_relative_to(owner.web)}
    assert client.poll() is None
    assert ingest_hellos(owner)==1
    assert client.poll()['payload']['blocked'] is False
    owner.command(client.device,True,'Wpisz kod');blocked=client.poll();assert state.blocked()
    code=owner.grant(client.device,90);assert verify_activation(code,config,client.device)['days']==90
    state.release();client.poll();assert not state.blocked()
    owner.command(client.device,True);client.poll();assert state.blocked()
    owner.command(client.device,False);client.poll();assert not state.blocked()
    assert RemoteState(state.folder).device()==client.device
    assert original=={p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file() and not p.is_relative_to(owner.web)}
    assert not any(p.name in ('management-signing.pem','automatic-key.enc','cache-key.bin') for p in parent.rglob('*'))

def test_signed_update_hash_and_payload_tampering(channel,tmp_path,monkeypatch):
    owner,config,state,client,parent=channel;client.poll();ingest_hellos(owner)
    installer=tmp_path/'installer.exe';installer.write_bytes(b'MZsynthetic-not-executed')
    release=owner.release(installer,'0.13.1',config['base_url']);owner.command(client.device,False,update=release)
    envelope=client.poll();cached=client.download(envelope,tmp_path/'cache');assert cached.read_bytes()==installer.read_bytes()
    cached.unlink();(owner.web/'updates'/cached.name).write_bytes(b'MZmodified')
    with pytest.raises(ValueError,match='rozmiar|SHA-256'):client.download(envelope,tmp_path/'cache')
    control=owner.web/'control'/(client.device+'.json');data=json.loads(control.read_bytes());data['payload']['blocked']=True;control.write_bytes(canonical(data))
    with pytest.raises(InvalidSignature):client.poll()
    assert not state.blocked()

def test_signed_update_defender_failure_never_executes(channel,tmp_path,monkeypatch):
    owner,config,state,client,_=channel;client.poll();ingest_hellos(owner)
    installer=tmp_path/'setup.exe';installer.write_bytes(b'MZtest');release=owner.release(installer,'0.13.1',config['base_url']);envelope=owner.command(client.device,False,update=release)
    root=tmp_path/'installed';root.mkdir();(root/'PDFManager.exe').write_bytes(b'MZtest')
    from pdfmanager.remote import updater
    monkeypatch.setattr(updater,'RemoteState',lambda:state)
    from pdfmanager.security import antivirus
    monkeypatch.setattr(antivirus,'scan_installer',MagicMock(side_effect=ValueError('Defender rejected')))
    run=MagicMock();restart=MagicMock()
    with pytest.raises(ValueError,match='Defender'):apply({'pid':123,'root':str(root),'installer':str(installer),'envelope':envelope},config,client.device,wait=lambda _:None,run=run,restart=restart)
    run.assert_not_called();restart.assert_not_called()

@pytest.mark.parametrize('group',['hello','control','updates'])
def test_redirected_channel_directories_cannot_touch_documents(channel,tmp_path,group):
    owner,config,state,client,parent=channel;client.poll();ingest_hellos(owner)
    target=owner.web/group;shutil.rmtree(target);outside=tmp_path/'documents';outside.mkdir();(outside/'important.pdf').write_bytes(b'DO NOT CHANGE');target.symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):scoped_target(owner.web,group,'example.json')
    if group=='hello':
        with pytest.raises(ValueError):client.poll()
        with pytest.raises(ValueError):ingest_hellos(owner)
    elif group=='control':
        with pytest.raises(ValueError):owner.command(client.device,True)
        with pytest.raises(ValueError):client.poll()
    else:
        installer=tmp_path/'setup.exe';installer.write_bytes(b'MZtest')
        with pytest.raises(ValueError):owner.release(installer,'0.13.1',config['base_url'])
    assert list(outside.iterdir())==[outside/'important.pdf'];assert (outside/'important.pdf').read_bytes()==b'DO NOT CHANGE'

def test_link_to_channel_root_is_rejected(channel,tmp_path):
    owner,config,_,_,_=channel
    link=tmp_path/owner.web.name;link.symlink_to(owner.web,target_is_directory=True)
    from pdfmanager.remote.shared import verify_folder
    assert not verify_folder(link,config)

def test_preexisting_symlink_new_child_does_not_write_documents(tmp_path):
    owner=AdminWorkspace(tmp_path/'private');automatic_unlock(owner);identity=str(uuid.uuid4())
    (owner.folder/'simple-connection.json').write_text(json.dumps({'workspace':identity}))
    parent=tmp_path/'drive';parent.mkdir();docs=tmp_path/'docs';docs.mkdir();(docs/'keep.pdf').write_bytes(b'original')
    (parent/('PDFManager-Polaczenie-'+identity[:8])).symlink_to(docs,target_is_directory=True)
    with pytest.raises(ValueError):attach_shared_folder(owner,parent)
    assert list(docs.iterdir())==[docs/'keep.pdf']

def test_marker_tamper_and_another_owner_rejected(channel,tmp_path):
    owner,config,state,client,_=channel
    marker=owner.web/MARKER;data=json.loads(marker.read_bytes());data['payload']['workspace']=str(uuid.uuid4());marker.write_bytes(canonical(data))
    with pytest.raises(OSError):client.poll()
    other=AdminWorkspace(tmp_path/'other');automatic_unlock(other)
    (other.folder/'simple-connection.json').write_text(json.dumps({'workspace':config['workspace']}))
    with pytest.raises(ValueError):attach_shared_folder(other,owner.web.parent)

def test_folder_relocation_and_offline_preserves_block(channel,tmp_path):
    owner,config,state,client,parent=channel;client.poll();ingest_hellos(owner);owner.command(client.device,True);client.poll();assert state.blocked()
    alternate=tmp_path/'other mount';alternate.mkdir();moved=alternate/owner.web.name;shutil.move(str(owner.web),moved)
    assert locate(config,[alternate])==moved
    client.poll();assert state.blocked()
    shutil.rmtree(moved)
    with pytest.raises(OSError):client.poll()
    assert state.blocked()

@pytest.mark.parametrize('suffix',['/../important.pdf','/updates/evil.exe','/control/../../important.pdf','/management-signing.pem'])
def test_arbitrary_paths_rejected(channel,suffix):
    _,config,_,_,_=channel
    with pytest.raises(ValueError):FolderTransport(config).open(Request(config['base_url']+suffix))

def test_other_workspace_request_rejected(channel):
    _,config,_,_,_=channel
    with pytest.raises(ValueError):FolderTransport(config).open(Request('pdm-share://'+str(uuid.uuid4())+'/hello',data=b'{}'))

def test_persist_pairing_for_updater_and_pin_owner(channel,tmp_path):
    owner,config,_,_,_=channel;factory=tmp_path/'management.json';factory.write_bytes(canonical(factory_envelope(config,owner.key)))
    folder=tmp_path/'config';assert load_config(factory=factory,folder=folder)==config
    assert b'pdm-share' not in (folder/'paired-config.enc').read_bytes()
    factory.unlink();assert load_config(factory=factory,folder=folder)==config
    other=AdminWorkspace(tmp_path/'other');automatic_unlock(other);new=attach_shared_folder(other,tmp_path)
    factory.write_bytes(canonical(factory_envelope(new,other.key)))
    with pytest.raises(ValueError,match='właściciela'):load_config(factory=factory,folder=folder)
    factory.unlink();assert load_config(factory=factory,folder=folder)==config

def test_unsigned_factory_cannot_bootstrap(channel,tmp_path):
    _,config,_,_,_=channel;factory=tmp_path/'management.json';factory.write_bytes(canonical(config))
    with pytest.raises((KeyError,ValueError)):load_config(factory=factory,folder=tmp_path/'config')

def test_owner_auto_key_reopens_locally_without_plaintext(channel):
    owner,_,_,_,_=channel;password=automatic_unlock(owner);assert password.encode() not in (owner.folder/'automatic-key.enc').read_bytes()
    second=AdminWorkspace(owner.folder);assert automatic_unlock(second)==password
    assert second.key.public_key().public_bytes_raw()==owner.key.public_key().public_bytes_raw()

def compiled(tmp_path):
    source=tmp_path/'build';source.mkdir();(source/'PDFManager.exe').write_bytes(b'MZdummy');(source/'PDFManagerUpdater.exe').write_bytes(b'MZdummyhelper')
    (source/'CLI').mkdir();(source/'CLI'/'PDFManagerCLI.exe').write_bytes(b'MZdummyCLI')
    (source/'PDFManager-build.json').write_text(json.dumps({'schema':1,'platform':'windows','version':'0.9.0'}))
    nested=source/'_internal';nested.mkdir();(nested/'data.dat').write_bytes(b'all dependencies')
    return source

def test_employee_package_is_complete_signed_and_prepaired(channel,tmp_path):
    owner,config,_,_,_=channel;source=compiled(tmp_path);destination=tmp_path/'company.zip';(source/'management.json').write_text('old config')
    prepare_package(source,destination,config,owner.key)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert archive.read('PDFManager/_internal/data.dat')==b'all dependencies'
        assert verify_factory(json.loads(archive.read('PDFManager/management.json')))==config
        assert not any('management-signing.pem' in n or 'automatic-key.enc' in n or 'cache-key.bin' in n for n in archive.namelist())
    assert (source/'management.json').read_text()=='old config'
    before=destination.read_bytes()
    with pytest.raises(FileExistsError):prepare_package(source,destination,config,owner.key)
    assert destination.read_bytes()==before

@pytest.mark.parametrize('private',['management-signing.pem','automatic-key.enc','cache-key.bin','secret.pfx','private.key','devices.json','paired-config.enc'])
def test_package_refuses_private_material(channel,tmp_path,private):
    owner,config,_,_,_=channel;source=compiled(tmp_path);(source/private).write_bytes(b'private');destination=tmp_path/'company.zip'
    with pytest.raises(ValueError):prepare_package(source,destination,config,owner.key)
    assert not destination.exists()

def test_package_refuses_old_build_and_private_pem(channel,tmp_path):
    owner,config,_,_,_=channel;source=compiled(tmp_path);manifest=source/'PDFManager-build.json';data=json.loads(manifest.read_text());data['version']='0.8.0';manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):prepare_package(source,tmp_path/'company.zip',config,owner.key)
    data['version']='0.9.0';manifest.write_text(json.dumps(data));(source/'secret.pem').write_bytes(b'-----BEGIN PRIVATE KEY-----')
    with pytest.raises(ValueError):prepare_package(source,tmp_path/'company.zip',config,owner.key)
    assert not (tmp_path/'company.zip').exists()

def test_package_refuses_links_to_other_files(channel,tmp_path):
    owner,config,_,_,_=channel;source=compiled(tmp_path);(source/'outside').symlink_to(tmp_path/'private',target_is_directory=True)
    with pytest.raises(ValueError):prepare_package(source,tmp_path/'company.zip',config,owner.key)

def test_installer_scan_is_mandatory_and_uses_no_remediation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from pdfmanager.security import antivirus
    from pdfmanager.dms import jobs
    from pdfmanager.dms.preferences import Preferences
    monkeypatch.setattr(antivirus,'os',SimpleNamespace(name='nt'))
    tool=tmp_path/'MpCmdRun.exe';tool.write_bytes(b'fake tool never executed');path=tmp_path/'installer.exe';path.write_bytes(b'MZtest')
    monkeypatch.setattr(antivirus,'executable',lambda:tool)
    monkeypatch.setattr(Preferences,'get',lambda *args:False)
    run=MagicMock(return_value=SimpleNamespace(returncode=0));monkeypatch.setattr(jobs,'run_process',run)
    assert antivirus.scan_installer(path)=='Scanned'
    assert '-DisableRemediation' in run.call_args.args[0]
    run.return_value.returncode=2
    with pytest.raises(ValueError):antivirus.scan_installer(path)
    monkeypatch.setattr(antivirus,'executable',lambda:None)
    with pytest.raises(ValueError):antivirus.scan_installer(path)

def test_tampering_during_update_scan_prevents_execution(channel,tmp_path,monkeypatch):
    owner,config,state,client,_=channel;client.poll();ingest_hellos(owner)
    installer=tmp_path/'setup.exe';installer.write_bytes(b'MZsafe');release=owner.release(installer,'0.13.1',config['base_url']);envelope=owner.command(client.device,False,update=release)
    root=tmp_path/'install';root.mkdir();(root/'PDFManager.exe').write_bytes(b'MZtest')
    from pdfmanager.remote import updater
    from pdfmanager.security import antivirus
    monkeypatch.setattr(updater,'RemoteState',lambda:state)
    monkeypatch.setattr(antivirus,'scan_installer',lambda path:path.write_bytes(b'MZevil'))
    run=MagicMock();restart=MagicMock()
    with pytest.raises(ValueError,match='Instalator'):apply({'pid':123,'root':str(root),'installer':str(installer),'envelope':envelope},config,client.device,wait=lambda _:None,run=run,restart=restart)
    run.assert_not_called();restart.assert_not_called()

def test_existing_unmarked_channel_is_not_overwritten(tmp_path):
    owner=AdminWorkspace(tmp_path/'private');automatic_unlock(owner);identity=str(uuid.uuid4())
    (owner.folder/'simple-connection.json').write_text(json.dumps({'workspace':identity}))
    parent=tmp_path/'drive';parent.mkdir();channel=parent/('PDFManager-Polaczenie-'+identity[:8]);channel.mkdir();(channel/'important.pdf').write_bytes(b'original')
    with pytest.raises(ValueError,match='pusty'):attach_shared_folder(owner,parent)
    assert list(channel.iterdir())==[channel/'important.pdf'];assert (channel/'important.pdf').read_bytes()==b'original'
