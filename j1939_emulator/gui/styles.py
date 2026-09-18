"""CSS from ImplementationPlan/standalone_v1.0.html for NiceGUI."""

APP_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body, .nicegui-content {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  background-color: #E8ECF0 !important;
  color: #1F2A37;
  font-size: 13px;
  line-height: 1.5;
}
.q-page, .nicegui-content { padding: 0 !important; }
.font-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }

.j1939-root { min-height: 100vh; display: flex; flex-direction: column; background: #E8ECF0; }
.topbar {
  height: 48px; background: #FFFFFF; border-bottom: 1px solid #CBD5E1;
  padding: 0 16px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
}
.brand-section { display: flex; align-items: center; gap: 10px; }
.brand-icon {
  width: 28px; height: 28px; background: #1F6FEB; color: white; border-radius: 3px;
  display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 14px;
}
.brand-title { font-weight: 800; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; color: #1F2A37; }
.badge-subtle {
  font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 3px;
  background: #E7F0FD; color: #1F6FEB; border: 1px solid #B6D4FE;
}
.status-pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 3px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.03em;
}
.status-pill.stopped { background: #F1F5F9; color: #64748B; border: 1px solid #CBD5E1; }
.status-pill.running { background: #EAF8F0; color: #1F9D55; border: 1px solid #A3E2BD; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.status-pill.stopped .status-dot { background: #94A3B8; }
.status-pill.running .status-dot { background: #1F9D55; }

.j1939-main {
  flex: 1; max-width: 1280px; width: 100%; margin: 0 auto; padding: 14px;
  display: flex; flex-direction: column; gap: 12px;
}
.card {
  background: #FFFFFF; border: 1px solid #C5CCD6; border-radius: 3px;
  padding: 12px 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
}
.bus-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.bus-controls-group { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; }
.field-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
  color: #5B6775; margin-bottom: 2px; display: block;
}
.action-btn {
  height: 30px; padding: 0 12px; font-size: 12px; font-weight: 700; border-radius: 3px;
  border: 1px solid transparent; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
}
.btn-start { background: #1F9D55; color: #FFFFFF; border-color: #1A8246; }
.btn-stop { background: #FFFFFF; color: #D32F2F; border-color: #C5CCD6; }
.btn-restart { background: #FFFFFF; color: #1F2A37; border-color: #C5CCD6; }
.btn-quit { background: #B91C1C; color: #FFFFFF; border-color: #991B1B; }
.btn-disabled { opacity: 0.5; pointer-events: none; }

.tab-bar {
  display: flex; background: #FFFFFF; border: 1px solid #C5CCD6; border-radius: 3px; overflow-x: auto;
}
.tab-btn {
  padding: 10px 16px; font-size: 12px; font-weight: 700; background: transparent; border: none;
  border-bottom: 2px solid transparent; color: #5B6775; cursor: pointer;
  display: inline-flex; align-items: center; gap: 8px; white-space: nowrap;
}
.tab-btn.active { color: #1F6FEB; border-bottom-color: #1F6FEB; background: #F4F8FD; }
.tab-pill {
  font-size: 10px; padding: 1px 5px; border-radius: 3px; background: #F1F5F9;
  color: #5B6775; border: 1px solid #CBD5E1;
}
.tab-btn.active .tab-pill { background: #E7F0FD; color: #1F6FEB; border-color: #B6D4FE; }
.tab-pill.warn {
  background: #FFFBEB;
  color: #B45309;
  border-color: #FDE68A;
}

.dtc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.dtc-card {
  background: #FFFFFF;
  border: 1px solid #CBD5E1;
  border-radius: 3px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dtc-card.fault-amber {
  background: #FFFBEB;
  border-color: #FBBF24;
  border-left: 4px solid #D97706;
}
.dtc-card.fault-red {
  background: #FEF2F2;
  border-color: #F87171;
  border-left: 4px solid #DC2626;
}

.pgn-card.pgn-hidden { display: none !important; }
.pgn-header {
  padding: 10px 12px; background: #F8FAFC; border-bottom: 1px solid #CBD5E1;
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px;
}
.pgn-title-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.badge-acronym {
  font-size: 11px; font-weight: 800; background: #1F6FEB; color: #FFFFFF;
  padding: 2px 6px; border-radius: 3px;
}
.pgn-name { font-weight: 700; font-size: 13px; color: #1F2A37; }
.payload-strip {
  padding: 6px 12px; background: #FAFBFD; border-bottom: 1px solid #E2E8F0;
  display: flex; align-items: center; justify-content: space-between; font-size: 11px; flex-wrap: wrap; gap: 6px;
}
.signal-box { padding: 10px 12px; border-bottom: 1px solid #F1F5F9; }
.signal-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.spn-badge {
  font-size: 10px; font-weight: 700; background: #F1F5F9; color: #475569;
  border: 1px solid #CBD5E1; border-radius: 3px; padding: 1px 5px; margin-right: 6px;
}
.signal-name { font-weight: 600; }
.signal-val { color: #1F2A37; }
.range-row { display: flex; align-items: center; gap: 10px; }
.preset-btn, .toggle-btn {
  font-size: 10px; padding: 2px 8px; border-radius: 3px; border: 1px solid #CBD5E1;
  background: #FFFFFF; color: #475569; cursor: pointer; font-family: inherit;
}
.toggle-btn.active { background: #1F6FEB; color: #FFFFFF; border-color: #1F6FEB; }
.toggle-btn.off-active { background: #64748B; color: #FFFFFF; border-color: #64748B; }

.j1939-footer {
  height: 26px; background: #E2E7ED; border-top: 1px solid #C5CCD6; padding: 0 14px;
  display: flex; align-items: center; justify-content: space-between; font-size: 11px;
  color: #5B6775; flex-shrink: 0;
}
.footer-left { display: flex; align-items: center; gap: 14px; }
.stub-pane {
  background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 3px; padding: 24px;
  color: #5B6775; font-size: 13px;
}
"""
