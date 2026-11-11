// FinanceCalculator: rent affordability (PB-08) and the home-loan EMI calculator.

import { $, html, mount, taka } from '../ui.js';

// A common planning rule: rent up to 30% of income is comfortable, up to 40% is a stretch.
const COMFORTABLE_SHARE = 0.3;
const STRETCH_SHARE = 0.4;

export function checkRentAffordability(monthlyIncome, monthlyRent) {
  const share = monthlyRent / monthlyIncome;
  const level = share <= COMFORTABLE_SHARE ? 'good' : share <= STRETCH_SHARE ? 'stretch' : 'bad';
  return { share, level, comfortableRent: Math.floor(monthlyIncome * COMFORTABLE_SHARE) };
}

export function calculateEmi(principal, annualRatePercent, years) {
  const months = years * 12;
  const rate = annualRatePercent / 1200;
  const emi = rate === 0 ? principal / months : (principal * rate * (1 + rate) ** months) / ((1 + rate) ** months - 1);
  return { emi, totalPaid: emi * months, totalInterest: emi * months - principal };
}

function readPositive(form, name, label, errors, { allowZero = false, max = 1e12 } = {}) {
  const raw = form[name].value.trim().replace(/,/g, '');
  const value = Number(raw);
  if (raw === '') errors[name] = `${label} is required.`;
  else if (!Number.isFinite(value)) errors[name] = `${label} must be a number.`;
  else if (value < 0) errors[name] = `${label} cannot be negative.`;
  else if (!allowZero && value === 0) errors[name] = `${label} must be more than 0.`;
  else if (value > max) errors[name] = `${label} is too large.`;
  return value;
}

function showFieldErrors(form, errors) {
  form.querySelectorAll('.field-error').forEach(node => node.remove());
  form.querySelectorAll('.has-error').forEach(node => node.classList.remove('has-error'));
  for (const [name, message] of Object.entries(errors)) {
    const field = form[name].closest('.field');
    field.classList.add('has-error');
    const note = document.createElement('span');
    note.className = 'field-error';
    note.textContent = message;
    field.append(note);
  }
  const first = Object.keys(errors)[0];
  if (first) form[first].focus();
  return !first;
}

const LEVEL_TEXT = {
  good: ['Affordable', 'This rent is within 30% of your income, a comfortable level for most households.'],
  stretch: ['A stretch', 'This rent takes 30–40% of your income. It can work, but leaves less for savings and bills.'],
  bad: ['Not affordable', 'This rent takes more than 40% of your income. Look for a lower rent or share the cost.'],
};

export async function render({ root, query }) {
  const tab = query.tab === 'emi' ? 'emi' : 'rent';
  mount(root, html`
    <div class="calc-wrap">
      <div class="page-head"><div><h1>Calculators</h1><p>Plan your budget before you contact an owner.</p></div></div>
      <nav class="tabs" aria-label="Calculator type">
        <a href="#/calculator?tab=rent" class="${tab === 'rent' ? 'active' : ''}">Rent affordability</a>
        <a href="#/calculator?tab=emi" class="${tab === 'emi' ? 'active' : ''}">Home loan EMI</a>
      </nav>
      <div class="panel">
      ${tab === 'rent' ? html`
        <form id="rent-form" novalidate>
          <div class="form-grid">
            <label class="field"><span>Monthly household income (৳)</span><input name="income" type="number" min="1" inputmode="numeric" placeholder="e.g. 120000"></label>
            <label class="field"><span>Monthly rent (৳)</span><input name="rent" type="number" min="1" inputmode="numeric" value="${query.rent || ''}" placeholder="e.g. 35000"></label>
          </div>
          <div class="form-actions"><button class="btn btn-primary" type="submit">Check affordability</button></div>
        </form>` : html`
        <form id="emi-form" novalidate>
          <div class="form-grid form-grid-3">
            <label class="field"><span>Loan amount (৳)</span><input name="principal" type="number" min="1" inputmode="numeric" value="${query.loan || ''}" placeholder="e.g. 5000000"></label>
            <label class="field"><span>Interest rate (% per year)</span><input name="rate" type="number" min="0" max="40" step="0.1" value="9"></label>
            <label class="field"><span>Loan term</span><select name="years">
              ${[5, 10, 15, 20, 25].map(years => html`<option value="${years}" ${years === 20 ? html`selected` : ''}>${years} years</option>`)}
            </select></label>
          </div>
          <div class="form-actions"><button class="btn btn-primary" type="submit">Calculate EMI</button></div>
        </form>`}
        <div id="calc-result" aria-live="polite"></div>
      </div>
      <p class="small muted">These are estimates for planning only, not financial advice.</p>
    </div>`);

  const result = $('#calc-result', root);
  const rentForm = $('#rent-form', root);
  rentForm?.addEventListener('submit', event => {
    event.preventDefault();
    const errors = {};
    const income = readPositive(rentForm, 'income', 'Monthly income', errors);
    const rent = readPositive(rentForm, 'rent', 'Monthly rent', errors);
    if (!showFieldErrors(rentForm, errors)) { mount(result, ''); return; }
    const { share, level, comfortableRent } = checkRentAffordability(income, rent);
    const [title, text] = LEVEL_TEXT[level];
    mount(result, html`<div class="result-card ${level}">
      <strong>${title}</strong>
      <p class="big">${Math.round(share * 100)}% of your income</p>
      <div class="meter" role="img" aria-label="${Math.round(share * 100)} percent of income"><span></span></div>
      <p>${text}</p>
      <p class="small">A comfortable rent for your income is up to <strong>${taka(comfortableRent)}</strong> a month.</p>
    </div>`);
    result.querySelector('.meter span').style.width = `${Math.min(100, share * 100)}%`;
  });

  const emiForm = $('#emi-form', root);
  emiForm?.addEventListener('submit', event => {
    event.preventDefault();
    const errors = {};
    const principal = readPositive(emiForm, 'principal', 'Loan amount', errors);
    const rate = readPositive(emiForm, 'rate', 'Interest rate', errors, { allowZero: true, max: 40 });
    if (!showFieldErrors(emiForm, errors)) { mount(result, ''); return; }
    const years = Number(emiForm.years.value);
    const { emi, totalPaid, totalInterest } = calculateEmi(principal, rate, years);
    mount(result, html`<div class="result-card">
      <strong>Estimated monthly EMI</strong>
      <p class="big">${taka(Math.round(emi))}</p>
      <p class="small">Over ${years} years you pay ${taka(Math.round(totalPaid))} in total, of which ${taka(Math.round(totalInterest))} is interest.</p>
    </div>`);
  });
}
