import express from 'express';
import cors from 'cors';
import { routes } from '@/routes';
import { errorHandler } from '@/middleware/error';
import { env } from '@/config/env';

if (process.env.LOAD_WORKERS === 'true') {
  import('./workers/email-sync.worker');
  import('./workers/email-processing.worker');
}

export const createApp = () => {
  const app = express();

  app.use(cors({
    origin: env.FRONTEND_URL,
    credentials: true,
  }));

  app.use(express.json({ limit: '10mb' }));
  app.use(express.urlencoded({ extended: true, limit: '10mb' }));

  app.use('/api', routes);

  app.use(errorHandler);

  return app;
};