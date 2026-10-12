from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import MagicMock,patch
import json,uuid,io,hashlib
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from pdfmanager.remote.protocol import sign,verify,version,config_check,stamp,verify_activation
from pdfmanager.remote.storage import RemoteState
from pdfmanager.remote.client import ControlClient,RedirectPolicy
from pdfmanager.remote.admin_backend import AdminWorkspace,serve
from pdfmanager.remote.updater import validate_plan,apply
from pdfmanager.licensing.license_manager import LicenseManager,LicenseState

@pytest.fixture
def setup(tmp_path,monkeypatch):
    from pdfmanager.licensing import secure_storage
    monkeypatch.setattr(secure_storage,'_registry',None)
    admin=AdminWorkspace(tmp_path/'admin');admin.unlock('very-long-test-password');state=RemoteState(tmp_path/'client');device=state.device();admin.register(device,'Anna');config=admin.configuration('https://example.test:8443')
    return admin,state,device,config

def control(admin,device,**kw):return admin.command(device,True,'Wpisz nowy kod.',**kw)

class Transport:
    def __init__(self,envelope,installer=b''):self.envelope=envelope;self.installer=installer
    def open(self,request,timeout=None):
        if request.full_url.endswith('/hello'):return io.BytesIO(b'')
        return io.BytesIO(json.dumps(self.envelope).encode() if '/control/' in request.full_url else self.installer)

def test_signature_device_and_expiry(setup):
    admin,state,device,config=setup;envelope=control(admin,device)
    assert verify(envelope,config['public_key'],device)['blocked']
    with pytest.raises(ValueError):verify(envelope,config['public_key'],str(uuid.uuid4()))
    with pytest.raises(ValueError):verify(envelope,config['public_key'],device,now=envelope['payload']['expires'])
    envelope['payload']['blocked']=False
    with pytest.raises(InvalidSignature):verify(envelope,config['public_key'],device)

def test_another_signer_rejected(setup):
    admin,state,device,config=setup;envelope=control(admin,device);forged=sign(envelope['payload'],Ed25519PrivateKey.generate())
    with pytest.raises(InvalidSignature):verify(forged,config['public_key'],device)

def test_block_persists_and_replay_cannot_clear_release(setup):
    admin,state,device,config=setup;blocked=control(admin,device);client=ControlClient(config,state,Transport(blocked));client.poll();assert state.blocked()
    state.release();assert not state.blocked();client.poll();assert not state.blocked()
    again=control(admin,device);client.transport=Transport(again);client.poll();assert state.blocked()
    older=admin.command(device,False);client.transport=Transport(older);client.poll();assert not state.blocked();client.transport=Transport(blocked);assert client.poll() is None;assert not state.blocked()

def test_update_after_activation_does_not_reblock(setup,tmp_path):
    admin,state,device,config=setup;blocked=control(admin,device);state.apply(blocked['payload']);state.release();assert not state.blocked()
    exe=tmp_path/'setup.exe';exe.write_bytes(b'MZsigned installer');update=admin.release(exe,'0.8.1',config['base_url']);payload=admin.command(device,True,update=update)['payload'];state.apply(payload);assert not state.blocked()

def test_offline_does_not_erase_block(setup):
    admin,state,device,config=setup;state.apply(control(admin,device)['payload']);transport=MagicMock();transport.open.side_effect=OSError('offline');client=ControlClient(config,state,transport)
    with pytest.raises(OSError):client.poll()
    assert state.blocked()

def test_unsigned_and_oversized_control_rejected(setup):
    admin,state,device,config=setup;client=ControlClient(config,state,Transport({'payload':{}}))
    with pytest.raises(ValueError):client.poll()
    transport=MagicMock();transport.open.return_value=io.BytesIO(b'x'*70000);client=ControlClient(config,state,transport)
    with pytest.raises(ValueError):client.poll()
    assert not state.blocked()

def test_https_and_redirects_enforced(setup):
    admin,state,device,config=setup
    for bad in ['http://example.test','https://user:password@example.test','file:///tmp/x','https://example.test/#x']:
        with pytest.raises(ValueError):config_check({**config,'base_url':bad})
    with pytest.raises(ValueError):RedirectPolicy(config['base_url']).redirect_request(MagicMock(),None,302,'',{},'https://other.example/file')

def test_download_verifies_hash_and_size(setup,tmp_path):
    admin,state,device,config=setup;exe=tmp_path/'a.exe';blob=b'MZsafe test, not executed';exe.write_bytes(blob);update=admin.release(exe,'0.8.1',config['base_url']);envelope=admin.command(device,False,update=update)
    client=ControlClient(config,state,Transport(envelope,blob));out=client.download(envelope,tmp_path/'cache');assert out.read_bytes()==blob
    out.unlink();client.transport.installer=b'MZtampered'
    with pytest.raises(ValueError):client.download(envelope,tmp_path/'cache')
    assert not out.exists();assert not list((tmp_path/'cache').glob('*.tmp'))

def test_download_rejects_other_origin(setup,tmp_path):
    admin,state,device,config=setup;blob=b'MZtest';update={'url':'https://other.example/a.exe','version':'0.8.1','size':len(blob),'sha256':hashlib.sha256(blob).hexdigest()};envelope=admin.command(device,False,update=update);client=ControlClient(config,state,Transport(envelope,blob))
    with pytest.raises(ValueError):client.download(envelope,tmp_path/'cache')
    assert not (tmp_path/'cache').exists()

def test_old_version_not_downloaded(setup,tmp_path):
    admin,state,device,config=setup;exe=tmp_path/'a.exe';exe.write_bytes(b'MZtest');update=admin.release(exe,'0.8.0',config['base_url']);envelope=admin.command(device,False,update=update);client=ControlClient(config,state,Transport(envelope,b'MZtest'));assert client.download(envelope,tmp_path/'cache') is None

def test_device_bound_one_use_activation(setup,tmp_path,monkeypatch):
    admin,state,device,config=setup
    import pdfmanager.remote.storage as storage
    monkeypatch.setattr(storage,'load_config',lambda:config);monkeypatch.setattr(storage,'RemoteState',lambda:state)
    manager=LicenseManager(tmp_path/'trial',tmp_path/'license');initial=manager.get_status();assert initial.days_remaining==182
    state.apply(control(admin,device)['payload']);assert manager.get_status().state==LicenseState.REMOTE_BLOCKED
    code=admin.grant(device,47);status=manager.activate(code);assert not status.is_blocked;assert 46<=status.days_remaining<=47
    from pdfmanager.licensing.license_key import LicenseKeyError
    with pytest.raises(LicenseKeyError):manager.activate(code)
    other=str(uuid.uuid4())
    with pytest.raises(ValueError):verify_activation(code,config,other)

def test_admin_unblock_does_not_extend_expired_license(setup,tmp_path,monkeypatch):
    admin,state,device,config=setup
    import pdfmanager.remote.storage as storage
    monkeypatch.setattr(storage,'load_config',lambda:config);monkeypatch.setattr(storage,'RemoteState',lambda:state)
    clock={'now':datetime(2026,1,1,tzinfo=timezone.utc)};manager=LicenseManager(tmp_path/'trial',tmp_path/'license',now_fn=lambda:clock['now']);manager.get_status();clock['now']=datetime(2026,10,12,tzinfo=timezone.utc)
    state.apply(control(admin,device)['payload']);assert manager.get_status().is_blocked
    state.apply(admin.command(device,False)['payload']);assert manager.get_status().state==LicenseState.EXPIRED

def test_legacy_code_cannot_bypass_remote_block(setup,tmp_path,monkeypatch,test_signing_key):
    admin,state,device,config=setup
    import pdfmanager.remote.storage as storage
    monkeypatch.setattr(storage,'load_config',lambda:config);monkeypatch.setattr(storage,'RemoteState',lambda:state)
    from pdfmanager.licensing.license_key import LicenseKeyError,generate_license_key
    state.apply(control(admin,device)['payload']);manager=LicenseManager(tmp_path/'trial',tmp_path/'license')
    with pytest.raises(LicenseKeyError):manager.activate(generate_license_key(test_signing_key,6))

def test_legacy_key_reuse_blocked_without_remote_config(tmp_path,test_signing_key,monkeypatch):
    import pdfmanager.remote.storage as storage
    monkeypatch.setattr(storage,'load_config',lambda:None)
    from pdfmanager.licensing.license_key import generate_license_key,LicenseKeyError
    manager=LicenseManager(tmp_path/'trial',tmp_path/'license');code=generate_license_key(test_signing_key,6);manager.activate(code)
    with pytest.raises(LicenseKeyError):manager.activate(code.lower().replace('-',' '))

def test_private_key_encrypted_and_not_in_public_root(setup):
    admin,state,device,config=setup;private=(admin.folder/'management-signing.pem').read_bytes();assert b'ENCRYPTED PRIVATE KEY' in private;assert not list(admin.web.rglob('*.pem'));assert 'PRIVATE KEY' not in json.dumps(config)
    with pytest.raises(ValueError):AdminWorkspace(admin.folder).unlock('wrong-password-123')

def test_updater_tamper_rejected_before_execution(setup,tmp_path):
    admin,state,device,config=setup;exe=tmp_path/'setup.exe';exe.write_bytes(b'MZtest');update=admin.release(exe,'0.8.1',config['base_url']);envelope=admin.command(device,False,update=update);root=tmp_path/'install';root.mkdir();(root/'PDFManager.exe').write_bytes(b'not executable');plan={'envelope':envelope,'installer':str(exe),'root':str(root),'pid':123}
    exe.write_bytes(b'MZtampered');run=MagicMock()
    with pytest.raises(ValueError):apply(plan,config,device,wait=MagicMock(),run=run,restart=MagicMock())
    run.assert_not_called()

def test_installer_runs_only_after_wait_and_recheck(setup,tmp_path):
    admin,state,device,config=setup;exe=tmp_path/'setup.exe';exe.write_bytes(b'MZtest');update=admin.release(exe,'0.8.1',config['base_url']);envelope=admin.command(device,False,update=update);root=tmp_path/'install';root.mkdir();(root/'PDFManager.exe').write_bytes(b'not executable');plan={'envelope':envelope,'installer':str(exe),'root':str(root),'pid':123}
    order=[];run=MagicMock(side_effect=lambda *a,**k:(order.append('run') or MagicMock(returncode=0)));restart=MagicMock(side_effect=lambda *a,**k:order.append('restart'))
    assert apply(plan,config,device,wait=lambda pid:order.append('wait'),run=run,restart=restart)=='0.8.1';assert order==['wait','run','restart'];assert run.call_args.args[0][1]=='/VERYSILENT'

def test_real_https_enrollment_control_and_private_path_denial(setup):
    from urllib.error import HTTPError
    from urllib.request import Request
    admin,state,device,config=setup;admin.create_tls('https://localhost','very-long-test-password');server=serve(admin,0,str(admin.folder/'tls-server.crt'),str(admin.folder/'tls-server.key'),'very-long-test-password',host='127.0.0.1')
    try:
        config=admin.configuration('https://localhost:'+str(server.server_address[1]));client=ControlClient(config,state);assert client.poll() is None
        assert admin.devices()[device]['version']=='0.8.0'
        control(admin,device);assert client.poll()['payload']['blocked'];assert state.blocked()
        with pytest.raises(HTTPError):client.transport.open(Request(config['base_url']+'/../management-signing.pem'),timeout=5)
        wrong=admin.configuration('https://127.0.0.1:'+str(server.server_address[1]));bad=ControlClient(wrong,state)
        with pytest.raises(Exception):bad.poll() # certificate hostname mismatch; verification is not bypassed.
    finally:server.shutdown();server.server_close()

def test_client_has_no_admin_menu_or_activation_button(qapp):
    from pdfmanager.ui.main_window import MainWindow
    from PySide6.QtWidgets import QPushButton
    win=MainWindow();labels=[a.text().casefold() for a in win._menu_help.actions()]
    assert not any('administr' in label for label in labels);assert win._shell.tabs.count()==8
    assert 'Aktywacja licencji' not in [b.text() for b in win._home_page.findChildren(QPushButton)];win.close()

def test_icons_use_real_hidpi_pixels(qapp):
    from PySide6.QtCore import QSize
    from pdfmanager.ui.vector_icons import vector_icon
    icon=vector_icon('save');pix=icon.pixmap(QSize(32,32),2.5);assert pix.width()==80 and pix.height()==80;assert pix.devicePixelRatio()==2.5
    assert not pix.toImage().isNull()

def test_license_dialog_in_window_does_not_bypass_safe_close(qapp,tmp_path):
    from PySide6.QtWidgets import QWidget
    from pdfmanager.ui.license_dialogs import ActivationDialog
    parent=QWidget();manager=LicenseManager(tmp_path/'trial',tmp_path/'license');dialog=ActivationDialog(manager,parent,allow_cancel=False)
    with patch.object(qapp,'quit') as quit_application:dialog._quit_application();quit_application.assert_not_called()
    assert dialog.result()==dialog.DialogCode.Rejected

def test_blocked_shortcuts_are_disabled_until_valid_activation(qapp):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.licensing.license_manager import LicenseStatus
    window=MainWindow();manager=MagicMock();manager.get_status.return_value=LicenseStatus(LicenseState.EXPIRED,0,datetime.now(timezone.utc));window.license_manager=manager
    with patch('pdfmanager.ui.main_window.ActivationDialog') as dialog,patch.object(window,'close'):
        instance=dialog.return_value
        def exec_dialog():
            assert not window._transport_actions['save_next'].isEnabled()
            assert not window._action_open_file.isEnabled()
            return instance.DialogCode.Rejected
        instance.exec.side_effect=exec_dialog;window._enforce_license_block()
    window.close()

def test_concurrent_state_keeps_device_and_highest_sequence(setup):
    from concurrent.futures import ThreadPoolExecutor
    admin,state,device,config=setup
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids=list(pool.map(lambda _:RemoteState(state.folder).device(),range(20)))
    assert set(ids)=={device}
    commands=[admin.command(device,True)['payload'] for _ in range(12)]
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(state.apply,reversed(commands)))
    assert state.read()['sequence']==12;assert state.blocked()

def test_minute_license_check_does_not_repeat_early_warning(qapp):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.licensing.license_manager import LicenseStatus
    window=MainWindow();manager=MagicMock();manager.get_status.return_value=LicenseStatus(LicenseState.TRIAL,6,datetime.now(timezone.utc));window.license_manager=manager
    with patch('pdfmanager.ui.main_window.ExpiryWarningDialog') as warning:
        warning.return_value.enter_key_requested=False;window._check_license_and_warn();window._check_license_and_warn();assert warning.return_value.exec.call_count==1
    window.close()

def test_closed_window_cannot_open_license_dialog_from_timer(qapp):
    from PySide6.QtTest import QTest
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.licensing.license_manager import LicenseStatus
    window=MainWindow();manager=MagicMock();manager.get_status.return_value=LicenseStatus(LicenseState.EXPIRED,0,datetime.now(timezone.utc));window.license_manager=manager;window._license_check_timer.setInterval(10)
    with patch.object(window,'_enforce_license_block') as blocked:
        window.close();QTest.qWait(50);blocked.assert_not_called()
    assert not window._license_check_timer.isActive()
