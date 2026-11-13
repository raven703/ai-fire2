"""Read-only UI layout checks; never publish or change the active policy."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def test_policy_layout_and_unsaved_changes():
    identities = json.loads(Path('/artifacts/.dlp-test-identities.json').read_text())
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--disable-dev-shm-usage'])
        try:
            for role in ('admin', 'auditor'):
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                identity = identities[role]
                page.goto('http://webui:8080/auth', wait_until='domcontentloaded')
                page.locator('input[name=email]').fill(identity['email'])
                page.locator('input[type=password]').first.fill(identity['password'])
                page.locator('button[type=submit]').click()
                expect(page.locator('#chat-input')).to_be_visible(timeout=40000)
                page.goto('http://webui:8080/admin/dlp', wait_until='domcontentloaded')
                expect(page.get_by_role('heading', name='Защита данных', exact=True)).to_be_visible()
                person = page.get_by_label('Action PERSON', exact=True)
                expect(person).to_be_visible()
                expect(page.get_by_role('heading', name='Корпоративные словари')).to_be_visible()
                if role == 'admin':
                    expect(person).to_be_enabled()
                    page.get_by_role('searchbox', name='Поиск категории').fill('фамилии')
                    expect(page.locator('.rule-row')).to_have_count(1)
                    page.get_by_role('searchbox', name='Поиск категории').fill('')
                    original = person.input_value()
                    person.select_option('BLOCK' if original != 'BLOCK' else 'MASK')
                    expect(page.get_by_role('button', name='Опубликовать черновик')).to_be_disabled()
                    expect(page.locator('.action-bar')).to_contain_text('Изменения ещё не сохранены')
                    person.select_option(original)
                    page.screenshot(path='/artifacts/dlp-settings-desktop.png', full_page=True)
                    page.evaluate("document.documentElement.classList.add('dark')")
                    page.screenshot(path='/artifacts/dlp-settings-dark.png', full_page=True)
                    page.evaluate("document.documentElement.classList.remove('dark')")
                    page.set_viewport_size({'width': 390, 'height': 844})
                    expect(person).to_be_visible()
                    assert page.locator('.dlp-page').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1')
                    page.screenshot(path='/artifacts/dlp-settings-mobile.png', full_page=True)
                else:
                    expect(person).to_be_disabled()
                    expect(page.get_by_role('button', name='Сохранить черновик')).to_be_disabled()
                assert not errors, errors
                context.close()
        finally:
            browser.close()