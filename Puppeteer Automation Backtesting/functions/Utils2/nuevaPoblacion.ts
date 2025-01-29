import { readdirSync, writeFileSync, readFileSync } from 'fs';
import axios from 'axios';
import FormData from 'form-data';
import { config } from 'dotenv';
import { join, resolve } from 'path';

config(); 
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

    const resultFiles = readdirSync(resultsDir).filter(file => file.startsWith(`results${assetName}`) && file.endsWith('.json'));
    const poblacionFiles = readdirSync(poblacionDir).filter(file => file.startsWith(`population${assetName}`) && file.endsWith('.json'));

    // Crear un array de índices (números) de resultados y poblaciones
    const resultIndices = resultFiles.map(file => parseInt(file.match(/\d+/)?.[0] || '0', 10));
    const poblacionIndices = poblacionFiles.map(file => parseInt(file.match(/\d+/)?.[0] || '0', 10));

    const missingResultIndex = poblacionIndices.find(index => !resultIndices.includes(index));

    if (missingResultIndex !== undefined) {
        const nextPoblacionFileName = `population${assetName}${missingResultIndex}.json`;
        const filePath = join(poblacionDir, nextPoblacionFileName);

        const poblacionData: { [key: string]: CombinationData } = JSON.parse(readFileSync(filePath, 'utf-8'));
        const resultFileName = `results${assetName}${missingResultIndex}.json`; 

        return { poblacionFileName: nextPoblacionFileName, poblacionData, resultFileName };
    } else {
        const nextIndex = Math.max(...poblacionIndices) + 1 || 1;
        const nextPoblacionFileName = `population${assetName}${nextIndex}.json`;

        // Preparar la solicitud para la API
        const formData = new FormData();
        resultFiles.forEach(file => formData.append('results', readFileSync(join(resultsDir, file))));
        formData.append('output_filename', nextPoblacionFileName.replace('.json', ''));
        formData.append('output_dir', poblacionDir);  

        try {
            const response = await axios.post(apiUrl, formData, {
                headers: formData.getHeaders()
            });

            console.log('Nueva población generada:', response.data.output_file);

            const generatedFilePath = resolve(poblacionDir, response.data.output_file);
            const poblacionData: { [key: string]: CombinationData } = JSON.parse(readFileSync(generatedFilePath, 'utf-8'));
            const resultFileName = `results${assetName}${nextIndex}.json`; 

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
