'use strict';
document.querySelectorAll('[data-password]').forEach(button => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.password);
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.textContent = visible ? 'Hide' : 'Show';
    button.setAttribute('aria-pressed', String(visible));
  });
});
const search = document.getElementById('searchCases');
const statusFilter = document.getElementById('statusFilter');
function filterCases() {
  const query = search.value.trim().toLowerCase();
  let matches = 0;
  document.querySelectorAll('.doctor-case').forEach(card => {
    const visible = (statusFilter.value === 'all' || card.dataset.status === statusFilter.value)
      && card.dataset.search.includes(query);
    card.hidden = !visible;
    if (visible) matches++;
  });
  document.getElementById('noMatches').hidden = matches !== 0;
}
if (search && statusFilter) {
  search.addEventListener('input', filterCases);
  statusFilter.addEventListener('change', filterCases);
}
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', () => {
    document.querySelectorAll('.nav-link').forEach(item => item.classList.remove('active'));
    link.classList.add('active');
  });
});
