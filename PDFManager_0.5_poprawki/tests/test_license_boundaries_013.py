"""Controlled-clock tests: actual six-month expiry, exact warning and UI gate."""
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import pytest
from pdfmanager.licensing import secure_storage
from pdfmanager.licensing.license_manager import LicenseManager,LicenseState,REGISTRY_KEY_PATH
from pdfmanager.licensing.license_key import generate_license_key,LicenseKeyError
from tests.conftest import FakeWinReg

@pytest.fixture
def setup(tmp_path,monkeypatch):
    registry=FakeWinReg();monkeypatch.setattr(secure_storage,'_registry',registry)
    clock={'now':datetime(2026,10,13,12,34,56,tzinfo=timezone.utc)}
    manager=LicenseManager(tmp_path/'trial',tmp_path/'license',now_fn=lambda:clock['now'])
    return manager,clock,registry

def test_warning_exactly_seven_days_not_seven_days_and_a_second(setup):
    manager,clock,_=setup;end=manager.get_status().expires_at
    assert end==datetime(2027,4,13,12,34,56,tzinfo=timezone.utc)
    clock['now']=end-timedelta(days=7,seconds=1);assert not manager.get_status().is_near_expiry
    clock['now']=end-timedelta(days=7);status=manager.get_status();assert status.days_remaining==7 and status.is_near_expiry
    clock['now']=end-timedelta(microseconds=1);assert not manager.get_status().is_blocked
    clock['now']=end;assert manager.get_status().state==LicenseState.EXPIRED

@pytest.mark.parametrize('start,end',[(datetime(2026,8,31,tzinfo=timezone.utc),datetime(2027,2,28,tzinfo=timezone.utc)),(datetime(2028,2,29,tzinfo=timezone.utc),datetime(2028,8,29,tzinfo=timezone.utc)),(datetime(2026,1,1,tzinfo=timezone.utc),datetime(2026,7,1,tzinfo=timezone.utc))])
def test_calendar_edges(setup,start,end):
    manager,clock,_=setup;clock['now']=start;assert manager.get_status().expires_at==end

def test_relaunch_and_loss_of_either_copy_do_not_restart_trial(setup):
    manager,clock,registry=setup;end=manager.get_status().expires_at;clock['now']+=timedelta(days=40)
    manager=LicenseManager(manager._trial_file,manager._license_file,now_fn=lambda:clock['now']);assert manager.get_status().expires_at==end
    registry.keys.clear();assert manager.get_status().expires_at==end
    manager._trial_file.unlink();assert manager.get_status().expires_at==end

def test_legacy_started_period_keeps_its_end_instead_of_resetting(setup):
    manager,clock,_=setup;start=clock['now']-timedelta(days=100)
    secure_storage.write_dual(REGISTRY_KEY_PATH,'trial',manager._trial_file,{'started_at':start.isoformat()})
    assert manager.get_status().expires_at==start+timedelta(days=182)

def test_clock_rollback_blocks_without_extending_trial(setup):
    manager,clock,_=setup;end=manager.get_status().expires_at;clock['now']+=timedelta(days=120);manager.get_status()
    clock['now']-=timedelta(days=100);assert manager.get_status().state==LicenseState.CLOCK_ERROR
    clock['now']+=timedelta(days=100);assert manager.get_status().expires_at==end

def test_invalid_and_reused_codes_cannot_extend_expiry(setup,test_signing_key):
    manager,clock,_=setup;before=manager.get_status().expires_at
    with pytest.raises(LicenseKeyError):manager.activate('not-a-code')
    assert manager.get_status().expires_at==before
    key=generate_license_key(test_signing_key,3);active=manager.activate(key);assert active.days_remaining==90
    clock['now']+=timedelta(days=1)
    with pytest.raises(LicenseKeyError):manager.activate(key)
    assert manager.get_status().expires_at==active.expires_at
    clock['now']=active.expires_at;assert manager.get_status().is_blocked

def test_missing_active_license_does_not_fall_back_to_trial(setup,test_signing_key):
    manager,clock,registry=setup;manager.get_status();manager.activate(generate_license_key(test_signing_key,3))
    manager._license_file.unlink();registry.keys[REGISTRY_KEY_PATH].pop('license')
    assert manager.get_status().is_blocked

def test_running_main_window_warns_then_disables_editing_and_requires_key(qapp,setup):
    from pdfmanager.ui.main_window import MainWindow
    manager,clock,_=setup;end=manager.get_status().expires_at;window=MainWindow(license_manager=manager)
    with patch('pdfmanager.ui.main_window.ExpiryWarningDialog') as warning:
        warning.return_value.enter_key_requested=False;clock['now']=end-timedelta(days=7);window._check_license_and_warn();warning.assert_called_once();window._check_license_and_warn();warning.assert_called_once()
    captured={}
    def blocked_exec(dialog):
        captured['workspace']=not window._workspace_stack.isEnabled();captured['word']=not window._word_format.isEnabled();captured['editor']=not window._text_properties.isEnabled();captured['cancel']=dialog._allow_cancel
        return dialog.DialogCode.Rejected
    clock['now']=end
    with patch('pdfmanager.ui.license_dialogs.ActivationDialog.exec',blocked_exec):window._check_license_and_warn()
    assert captured=={'workspace':True,'word':True,'editor':True,'cancel':False}
    window.close()

def test_accepted_dialog_without_valid_activation_cannot_bypass_start_gate(qapp,setup):
    from pdfmanager.main import _run_license_gate
    manager,clock,_=setup;clock['now']=manager.get_status().expires_at
    with patch('pdfmanager.main.ActivationDialog') as dialog:
        dialog.return_value.exec.return_value=dialog.return_value.DialogCode.Accepted
        assert _run_license_gate(manager) is False

def test_real_qt_timer_blocks_at_expiry_and_valid_code_restores_controls(qapp,tmp_path,monkeypatch,test_signing_key):
    from PySide6.QtTest import QTest
    from pdfmanager.ui.main_window import MainWindow
    monkeypatch.setattr(secure_storage,'_registry',FakeWinReg())
    manager=LicenseManager(tmp_path/'trial',tmp_path/'license');manager.get_status()
    expiry=datetime.now(timezone.utc)+timedelta(seconds=1.2)
    secure_storage.write_dual(REGISTRY_KEY_PATH,'license',manager._license_file,{'expires_at':expiry.isoformat()})
    window=MainWindow(license_manager=manager);calls=[];key=generate_license_key(test_signing_key,3)
    def activate(dialog):
        calls.append(not window._workspace_stack.isEnabled() and not window._word_format.isEnabled())
        assert manager.get_status().is_blocked
        assert not manager.activate(key).is_blocked
        return dialog.DialogCode.Accepted
    with patch('pdfmanager.ui.main_window.ExpiryWarningDialog') as warning,patch('pdfmanager.ui.license_dialogs.ActivationDialog.exec',activate):
        warning.return_value.enter_key_requested=False;window._check_license_and_warn();QTest.qWait(2400)
    assert calls==[True]
    assert window._workspace_stack.isEnabled() and window._word_format.isEnabled()
    assert manager.get_status().state==LicenseState.LICENSED
    window.close()

def test_signed_remote_block_forces_dialog_and_new_bound_code_unlocks(qapp,tmp_path,monkeypatch):
    from pdfmanager.remote.admin_backend import AdminWorkspace
    from pdfmanager.remote.storage import RemoteState
    from pdfmanager.remote.protocol import verify
    from pdfmanager.ui.main_window import MainWindow
    monkeypatch.setattr(secure_storage,'_registry',None)
    owner=AdminWorkspace(tmp_path/'owner');owner.unlock('long-test-password-013');state=RemoteState(tmp_path/'remote');device=state.device();owner.register(device,'Test device');config=owner.configuration('https://example.test:8443')
    manager=LicenseManager(tmp_path/'trial',tmp_path/'license');manager.get_status();window=MainWindow(license_manager=manager)
    envelope=owner.command(device,True,'Test block');state.apply(verify(envelope,config['public_key'],device));captured=[]
    def enter_code(dialog):
        captured.append(not window._workspace_stack.isEnabled())
        assert manager.get_status().state==LicenseState.REMOTE_BLOCKED
        code=owner.grant(device,14);assert manager.activate(code).days_remaining==14
        return dialog.DialogCode.Accepted
    with patch('pdfmanager.remote.storage.load_config',return_value=config),patch('pdfmanager.remote.storage.RemoteState',return_value=state),patch('pdfmanager.ui.license_dialogs.ActivationDialog.exec',enter_code):
        window._check_license_and_warn();assert not manager.get_status().is_blocked
    assert captured==[True] and window._workspace_stack.isEnabled();window.close()

def test_helper_cannot_perform_pdf_operation_when_access_blocked(qapp,monkeypatch,tmp_path):
    from pdfmanager.security import worker
    from pdfmanager.licensing.license_manager import LicenseStatus
    from unittest.mock import MagicMock
    manager=MagicMock();manager.get_status.return_value=LicenseStatus(LicenseState.EXPIRED,0,datetime.now(timezone.utc))
    organization=qapp.organizationName();application=qapp.applicationName()
    try:
        with patch('pdfmanager.licensing.license_manager.get_default_license_manager',return_value=manager):
            with pytest.raises(PermissionError):worker.require_access()
    finally:qapp.setOrganizationName(organization);qapp.setApplicationName(application)

def test_expiry_at_worker_commit_keeps_previous_output(qapp,monkeypatch,tmp_path):
    from pdfmanager.security import worker,isolation
    from pdfmanager.pdf_engine.io_utils import atomic_write_bytes
    target=tmp_path/'result.pdf';target.write_bytes(b'previous')
    with patch.object(isolation,'WORKER_MODE',True),patch.object(worker,'ACCESS_REQUIRED',True),patch.object(worker,'require_access',side_effect=PermissionError('expired')):
        with pytest.raises(PermissionError):atomic_write_bytes(target,b'replacement')
    assert target.read_bytes()==b'previous'
