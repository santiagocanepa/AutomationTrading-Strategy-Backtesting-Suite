import { main } from './main.js';

async function start() {
    try {
        await main();
    } catch (error) {
        if (error instanceof Error) {
            console.error('Error:', error.message);
        } else {
            console.error('Error desconocido:', error);
        }
    }
}

// Iniciar el proceso
start();
