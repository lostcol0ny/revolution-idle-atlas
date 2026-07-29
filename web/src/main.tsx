import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './ui/styles.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('#root element is missing from index.html');
}

createRoot(container).render(
  <StrictMode>
    <p>Revolution Idle Atlas</p>
  </StrictMode>,
);
