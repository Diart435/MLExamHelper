import { useParams, useNavigate } from 'react-router-dom';
import './MaterialsPage.css';

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M12 16V5m0 0L7.5 9.5M12 5l4.5 4.5"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M4 15.5v2A2.5 2.5 0 006.5 20h11a2.5 2.5 0 002.5-2.5v-2"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
    />
  </svg>
);

const MaterialsPage = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();

  if (!courseId) {
    return (
      <div className="materials-page">
        <div className="materials-page__pattern" aria-hidden="true" />
        <div className="materials-page__content">
          <div className="materials-state is-error">
            <p>Курс не найден</p>
            <span>Вернитесь к списку курсов и откройте материалы нужного курса.</span>
            <button
              type="button"
              className="materials-state__retry"
              onClick={() => navigate('/courses')}
            >
              Ко всем курсам
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="materials-page">
      <div className="materials-page__pattern" aria-hidden="true" />

      <div className="materials-page__content">
        <section className="materials-block">
          <div className="materials-tab">Загрузка материала</div>

          <div className="materials-panel materials-panel--upload">
            <div className="upload-zone">
              <span className="upload-zone__icon">
                <UploadIcon />
              </span>
              <h2 className="upload-zone__title">Загрузите материалы</h2>
              <p className="upload-zone__hint">
                Перетащите файлы сюда или выберите на устройстве
              </p>
              <p className="upload-zone__formats">PDF или DOCX · до 50 МБ</p>

              <div className="upload-zone__actions">
                <button type="button" className="materials-btn materials-btn--outline">
                  Выберите файлы
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="materials-block">
          <div className="materials-tab">
            Материалы
            <span className="materials-tab__count">0</span>
          </div>
          <div className="materials-panel materials-panel--list">
            <div className="materials-placeholder">
              Список материалов курса появится здесь.
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default MaterialsPage;
