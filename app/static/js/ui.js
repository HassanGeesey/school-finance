/* UI helpers for the School Finance shell: modals, toasts, confirm dialogs,
 * loading states, sidebar toggling, Esc handling. Loaded after htmx.
 *
 * Declarative hooks (wire behavior purely from markup):
 *   data-modal-open="<element-id>"   opens that <dialog> via showModal()
 *   data-modal-close                 closes the enclosing <dialog>
 * Esc closes the topmost open dialog, unless focus is in an editable field.
 */
(function () {
  'use strict';

  var toastContainer = function () {
    var el = document.getElementById('toast-container');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast-container';
      el.className = 'toast toast-top toast-end z-50';
      document.body.appendChild(el);
    }
    return el;
  };

  function showToast(message, tone) {
    var el = document.createElement('div');
    el.className = 'toast-item toast-' + (tone || 'info');
    el.setAttribute('role', 'status');
    el.textContent = message;
    toastContainer().appendChild(el);
    setTimeout(function () {
      el.classList.add('toast-leaving');
      setTimeout(function () { el.remove(); }, 300);
    }, 4000);
  }

  function isEditable(el) {
    if (!el) return false;
    var tag = el.tagName;
    return tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || el.isContentEditable === true;
  }

  function openModalById(id) {
    var target = id ? document.getElementById(id) : null;
    if (target && typeof target.showModal === 'function') {
      target.showModal();
      return true;
    }
    return false;
  }

  function closeEnclosingModal(el) {
    var dialog = el.closest ? el.closest('dialog') : null;
    if (dialog && typeof dialog.close === 'function') dialog.close();
  }

  // Declarative modal wiring: openers and closers never need bespoke JS.
  document.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-modal-open]');
    if (opener) {
      if (!openModalById(opener.getAttribute('data-modal-open'))) {
        event.preventDefault();
      }
      return;
    }
    var closer = event.target.closest('[data-modal-close]');
    if (closer) {
      event.preventDefault();
      closeEnclosingModal(closer);
    }
  });

  // Esc closes the topmost open dialog app-wide; typing stays untouched
  // (native <dialog> Esc behavior keeps working regardless).
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    if (isEditable(document.activeElement)) return;
    var open = document.querySelectorAll('dialog[open]');
    if (open.length > 0) {
      var top = open[open.length - 1];
      if (typeof top.close === 'function') top.close();
    }
  });

  function openConfirmDialog(message, onConfirm) {
    var dialog = document.getElementById('confirm-dialog');
    if (!dialog) return false;
    var text = dialog.querySelector('[data-confirm-message]');
    if (text) text.textContent = message;
    var accept = dialog.querySelector('[data-confirm-accept]');
    var cancel = dialog.querySelector('[data-confirm-cancel]');
    function cleanup() {
      dialog.removeEventListener('close', onClose);
      accept.onclick = null;
      cancel.onclick = null;
    }
    function onClose() { cleanup(); }
    dialog.addEventListener('close', onClose);
    accept.onclick = function () { dialog.close(); onConfirm(); };
    cancel.onclick = function () { dialog.close(); };
    dialog.showModal();
    return true;
  }

  function needsConfirmation(el) {
    return typeof el.dataset.confirm === 'string' && el.dataset.confirm.length > 0;
  }

  function performAction(el) {
    var form = el.tagName === 'FORM' ? el : el.form;
    if (form) {
      // Pass the confirmed element as the submitter so its formaction /
      // formnovalidate are honoured (e.g. the fee-item "Remove" button).
      if (el.tagName === 'BUTTON' || el.tagName === 'INPUT') {
        form.requestSubmit(el);
      } else {
        form.requestSubmit();
      }
    } else if (el.tagName === 'A') {
      var href = el.getAttribute('href');
      if (href) window.location.href = href;
    } else {
      el.click();
    }
  }

  document.addEventListener('click', function (event) {
    var el = event.target.closest('[data-confirm]');
    if (!el) return;
    if (el.dataset.confirmed === 'true') {
      el.dataset.confirmed = 'false';
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    openConfirmDialog(el.dataset.confirm, function () {
      el.dataset.confirmed = 'true';
      performAction(el);
    });
  });

  document.addEventListener('click', function (event) {
    var row = event.target.closest('tr[data-row-href]');
    if (!row) return;
    if (event.target.closest('a, button')) return;
    window.location.href = row.dataset.rowHref;
  });

  function setLoading(el, loading) {
    if (el && el.classList.contains('btn')) el.classList.toggle('btn-loading', loading);
  }

  if (window.htmx) {
    document.body.addEventListener('htmx:beforeRequest', function (e) {
      setLoading(e.target, true);
    });
    document.body.addEventListener('htmx:afterRequest', function (e) {
      setLoading(e.target, false);
      var header = e.detail && e.detail.xhr ? e.detail.xhr.getResponseHeader('HX-Trigger') : null;
      if (!header) return;
      var parsed = null;
      try { parsed = JSON.parse(header); } catch (err) { return; }
      if (parsed && parsed.toast) {
        showToast(parsed.toast.message, parsed.toast.tone || 'info');
      }
    });
    document.body.addEventListener('htmx:responseError', function (e) {
      setLoading(e.target, false);
      showToast('Something went wrong. Please try again.', 'error');
    });
    document.body.addEventListener('htmx:sendError', function (e) {
      setLoading(e.target, false);
      showToast('Could not reach the server.', 'error');
    });
  }

  var toggle = document.getElementById('sidebar-toggle');
  var backdrop = document.getElementById('sidebar-backdrop');
  if (toggle) {
    toggle.addEventListener('click', function () {
      document.body.classList.toggle('sidebar-open');
    });
  }
  if (backdrop) {
    backdrop.addEventListener('click', function () {
      document.body.classList.remove('sidebar-open');
    });
  }

  document.querySelectorAll('[data-password-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.querySelector(btn.dataset.passwordToggle);
      if (!input) return;
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      btn.querySelectorAll('[data-icon]').forEach(function (el) {
        el.classList.toggle('hidden', el.dataset.icon === (show ? 'eye' : 'eye-slash'));
      });
    });
  });

  window.showToast = showToast;
})();
