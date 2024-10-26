import { readdirSync, writeFileSync, readFileSync } from 'fs';
import axios from 'axios';
import FormData from 'form-data';
import { config } from 'dotenv';
import { join, resolve } from 'path';

config(); // Cargar variables de entorno desde un archivo .env

interface CombinationData {
    name: string;
    indicators: { [key: string]: string };
    riskManagement: { [key: string]: string | number };
    requires: { [key: string]: number };
}

export async function nuevaPoblacion(): Promise<{ poblacionFileName: string, poblacionData: { [key: string]: CombinationData }, resultFileName: string }> {
    const resultsDir = process.env.RESULTS_DIR || './Results';
    const poblacionDir = process.env.POBLACION_DIR || './Poblaciones';
    const apiUrl = 'http://localhost:5500/generate_population';
    const assetName = process.env.ASSET_NAME || 'DEFAULT';

    // Leer todos los archivos en las carpetas
    const resultFiles = readdirSync(resultsDir).filter(file => file.startsWith(`results${assetName}`) && file.endsWith('.json'));
    const poblacionFiles = readdirSync(poblacionDir).filter(file => file.startsWith(`population${assetName}`) && file.endsWith('.json'));

    // Crear un array de índices (números) de resultados y poblaciones
    const resultIndices = resultFiles.map(file => parseInt(file.match(/\d+/)?.[0] || '0', 10));
    const poblacionIndices = poblacionFiles.map(file => parseInt(file.match(/\d+/)?.[0] || '0', 10));

    // Buscar el primer índice de población que no tenga un archivo de resultados correspondiente
    const missingResultIndex = poblacionIndices.find(index => !resultIndices.includes(index));

    if (missingResultIndex !== undefined) {
        // Existe una población sin un resultado correspondiente
        const nextPoblacionFileName = `population${assetName}${missingResultIndex}.json`;
        const filePath = join(poblacionDir, nextPoblacionFileName);

        const poblacionData: { [key: string]: CombinationData } = JSON.parse(readFileSync(filePath, 'utf-8'));
        const resultFileName = `results${assetName}${missingResultIndex}.json`; // Generar nombre de archivo de resultados

        return { poblacionFileName: nextPoblacionFileName, poblacionData, resultFileName };
    } else {
        // Todos los índices tienen un archivo de resultados correspondiente, generar una nueva población
        const nextIndex = Math.max(...poblacionIndices) + 1 || 1;
        const nextPoblacionFileName = `population${assetName}${nextIndex}.json`;

        // Preparar la solicitud para la API
        const formData = new FormData();
        resultFiles.forEach(file => formData.append('results', readFileSync(join(resultsDir, file))));
        formData.append('output_filename', nextPoblacionFileName.replace('.json', ''));
        formData.append('output_dir', poblacionDir);  // Añadir el directorio de salida

        try {
            const response = await axios.post(apiUrl, formData, {
                headers: formData.getHeaders()
            });

            console.log('Nueva población generada:', response.data.output_file);

            // Guardar el archivo recibido en la carpeta de poblaciones
            const generatedFilePath = resolve(poblacionDir, response.data.output_file); // Usar resolve para evitar la doble concatenación
            const poblacionData: { [key: string]: CombinationData } = JSON.parse(readFileSync(generatedFilePath, 'utf-8'));
            const resultFileName = `results${assetName}${nextIndex}.json`; // Generar nombre de archivo de resultados

            return { poblacionFileName: nextPoblacionFileName, poblacionData, resultFileName };
        } catch (error: unknown) {
            if (error instanceof Error) {
                console.error('Error al generar la nueva población:', error.message);
            } else {
                console.error('Error desconocido:', error);
            }
        }
    }

    return { poblacionFileName: '', poblacionData: {}, resultFileName: '' };
}
